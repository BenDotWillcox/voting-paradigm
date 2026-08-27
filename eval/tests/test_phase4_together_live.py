from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from pydantic import JsonValue, SecretStr, TypeAdapter, ValidationError

from eval.contracts import ContractModel
from eval.fixture_io import content_sha256
from eval.phase4_capability import CapabilityInterviewerTools
from eval.phase4_interviewer import (
    AskVettedQuestionDecision,
    ReadCandidateQuestionScoresResult,
    VettedQuestionCandidate,
)
from eval.phase4_provider import (
    ProviderBudgetRuntime,
    ProviderCallOutcome,
    ProviderResponseContract,
    build_public_development_attestation,
    prepare_provider_request,
    provider_request_content_sha256,
    price_provider_tokens,
)
from eval.phase4_provider_semantics import (
    build_public_capability_question,
    provider_response_adapter_for_role,
)
from eval.phase4_robustness import (
    BudgetSegment,
    LLMRole,
    load_phase4_robustness_profile,
)
from eval.phase4_together import (
    Phase4TogetherSuite,
    load_together_suite,
    tool_definitions_for_role,
)
from eval.phase4_together_live import (
    TogetherAccountPrivacyAttestation,
    TogetherAmbiguousDeliveryError,
    TogetherAuthorizedProviderRequest,
    TogetherCandidateTokenProjection,
    TogetherCatalogPreflightBundle,
    TogetherCatalogPreflightClient,
    TogetherCapabilityPreflightReceipt,
    TogetherPayloadTokenCount,
    TogetherTokenReadinessReceipt,
    TogetherHTTPTransport,
    TogetherHeadroomPolicy,
    TogetherLiveAuthorization,
    TogetherInterviewerToolExecutor,
    TogetherPaidStage,
    TogetherPublicSourceCheck,
    TogetherPublicSourceReverification,
    build_catalog_preflight_authorization,
    build_catalog_preflight_receipt,
    fetch_public_source_reverification,
    load_together_api_key,
)
from eval.preflight_phase4_together import (
    _context_window_diagnostics,
    main as catalog_preflight_main,
)

ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = (
    ROOT / "eval/fixtures/preference_eval_phase4_robustness_v1.json"
)
SUITE_PATH = ROOT / "eval/fixtures/preference_eval_phase4_together_v3.json"
SUITE_V5_PATH = ROOT / "eval/fixtures/preference_eval_phase4_together_v5.json"
NOW = datetime(2026, 8, 21, 15, 0, tzinfo=timezone.utc)


class DemoOutput(ContractModel):
    choice: str
    confidence: float


OUTPUT_ADAPTER = ProviderResponseContract(adapter=TypeAdapter(DemoOutput))


def profile():
    return load_phase4_robustness_profile(PROFILE_PATH)


def suite() -> Phase4TogetherSuite:
    return load_together_suite(SUITE_PATH)


def account_attestation(
    loaded: Phase4TogetherSuite,
) -> TogetherAccountPrivacyAttestation:
    return TogetherAccountPrivacyAttestation(
        attestation_id="together_account_privacy_test",
        attestation_version=1,
        together_suite_id=loaded.suite_id,
        together_suite_version=loaded.suite_version,
        together_suite_sha256=content_sha256(loaded),
        provider_terms_sha256=content_sha256(loaded.provider_terms),
        checked_at=NOW,
    )


def public_sources(
    loaded: Phase4TogetherSuite,
) -> TogetherPublicSourceReverification:
    urls = {
        loaded.catalog.source_url,
        loaded.provider_terms.privacy_source_url,
        loaded.provider_terms.parameters_source_url,
        loaded.provider_terms.structured_outputs_source_url,
        *(
            artifact.weight_manifest.revision_tree_url
            for artifact in loaded.candidates
        ),
        *(
            artifact.license_provenance.license_source_url
            for artifact in loaded.candidates
        ),
    }
    return TogetherPublicSourceReverification(
        receipt_id="together_public_sources_test",
        receipt_version=1,
        together_suite_id=loaded.suite_id,
        together_suite_version=loaded.suite_version,
        together_suite_sha256=content_sha256(loaded),
        checked_at=NOW,
        source_checks=[
            TogetherPublicSourceCheck(
                source_url=url,
                response_sha256=content_sha256({"url": url}),
            )
            for url in sorted(urls)
        ],
    )


def catalog_authorization(loaded: Phase4TogetherSuite):
    return build_catalog_preflight_authorization(
        loaded,
        account_attestation(loaded),
        public_sources(loaded),
        authorization_id="together_catalog_preflight_test",
        approved_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def live_model_payload(loaded: Phase4TogetherSuite) -> list[object]:
    return [
        {
            "id": artifact.candidate.serving_model_id,
            "context_length": artifact.candidate.context_window_tokens,
            "pricing": {
                "input": str(
                    Decimal(
                        artifact.price_card.input_microusd_per_million_tokens
                    )
                    / Decimal(1_000_000)
                ),
                "output": str(
                    Decimal(
                        artifact.price_card.output_microusd_per_million_tokens
                    )
                    / Decimal(1_000_000)
                ),
            },
        }
        for artifact in loaded.candidates
    ]


def catalog_receipt(loaded: Phase4TogetherSuite):
    return build_catalog_preflight_receipt(
        loaded,
        catalog_authorization(loaded),
        live_model_payload(loaded),
        receipt_id="together_catalog_receipt_test",
        checked_at=NOW,
    )


def catalog_bundle(loaded: Phase4TogetherSuite) -> TogetherCatalogPreflightBundle:
    return TogetherCatalogPreflightBundle(
        bundle_id="together_catalog_bundle_test",
        bundle_version=1,
        account_privacy_attestation=account_attestation(loaded),
        public_source_reverification=public_sources(loaded),
        authorization=catalog_authorization(loaded),
        receipt=catalog_receipt(loaded),
    )


def token_readiness(
    loaded: Phase4TogetherSuite,
) -> TogetherTokenReadinessReceipt:
    qualification_usage = (
        loaded.workload.qualification_per_candidate.role_usage
    )
    held_out_usage = loaded.workload.held_out_selected_candidate.role_usage
    qualification_count = sum(
        item.request_count
        for item in qualification_usage
    )
    held_out_count = sum(
        item.request_count
        for item in held_out_usage
    )
    return TogetherTokenReadinessReceipt(
        receipt_id="together_exact_projection_test",
        receipt_version=1,
        together_suite_id=loaded.suite_id,
        together_suite_version=loaded.suite_version,
        together_suite_sha256=content_sha256(loaded),
        workload_sha256=content_sha256(loaded.workload),
        created_at=NOW,
        candidate_projections=[
            TogetherCandidateTokenProjection(
                candidate_id=artifact.candidate.candidate_id,
                candidate_sha256=content_sha256(artifact.candidate),
                tokenizer_id=f"{artifact.candidate.candidate_id}_tokenizer",
                tokenizer_version=1,
                tokenizer_artifact_sha256=content_sha256(
                    {
                        "candidate": artifact.candidate.candidate_id,
                        "revision": artifact.candidate.upstream_model_revision,
                    }
                ),
                qualification_request_manifest_sha256=content_sha256(
                    [artifact.candidate.candidate_id, "qualification"]
                ),
                qualification_request_count=qualification_count,
                qualification_input_token_count=qualification_count * 10,
                qualification_output_token_upper_bound_count=(
                    qualification_count * 5
                ),
                qualification_projected_cost_microusd=(
                    qualification_count
                    * price_provider_tokens(
                        artifact.price_card,
                        input_tokens=10,
                        output_tokens=5,
                    )
                ),
                qualification_max_single_call_authorization_microusd=max(
                    price_provider_tokens(
                        artifact.price_card,
                        input_tokens=item.input_tokens_per_request,
                        output_tokens=item.output_tokens_per_request,
                    )
                    for item in qualification_usage
                ),
                qualification_all_calls_at_envelope_cost_microusd=sum(
                    item.request_count
                    * price_provider_tokens(
                        artifact.price_card,
                        input_tokens=item.input_tokens_per_request,
                        output_tokens=item.output_tokens_per_request,
                    )
                    for item in qualification_usage
                ),
                held_out_calibration_manifest_sha256=content_sha256(
                    [artifact.candidate.candidate_id, "held_out"]
                ),
                held_out_calibration_request_count=held_out_count,
                held_out_input_token_count=held_out_count * 20,
                held_out_output_token_upper_bound_count=held_out_count * 10,
                held_out_projected_cost_microusd=(
                    held_out_count
                    * price_provider_tokens(
                        artifact.price_card,
                        input_tokens=20,
                        output_tokens=10,
                    )
                ),
                held_out_max_single_call_authorization_microusd=max(
                    price_provider_tokens(
                        artifact.price_card,
                        input_tokens=item.input_tokens_per_request,
                        output_tokens=item.output_tokens_per_request,
                    )
                    for item in held_out_usage
                ),
                held_out_all_calls_at_envelope_cost_microusd=sum(
                    item.request_count
                    * price_provider_tokens(
                        artifact.price_card,
                        input_tokens=item.input_tokens_per_request,
                        output_tokens=item.output_tokens_per_request,
                    )
                    for item in held_out_usage
                ),
            )
            for artifact in loaded.candidates
        ],
    )


def headroom_policy() -> TogetherHeadroomPolicy:
    return TogetherHeadroomPolicy(
        policy_id="together_headroom_test",
        policy_version=1,
        created_at=NOW,
        qualification_minimum_headroom_microusd=100_000,
        held_out_minimum_headroom_microusd=100_000,
    )


def live_authorization(
    loaded: Phase4TogetherSuite,
    *,
    stage: TogetherPaidStage = TogetherPaidStage.CAPABILITY_PREFLIGHT,
    budget_segment: BudgetSegment = BudgetSegment.QUALIFICATION,
    capability_receipt: TogetherCapabilityPreflightReceipt | None = None,
    projection: TogetherTokenReadinessReceipt | None = None,
    headroom: TogetherHeadroomPolicy | None = None,
) -> TogetherLiveAuthorization:
    exact = projection or token_readiness(loaded)
    policy = headroom or headroom_policy()
    return TogetherLiveAuthorization(
        authorization_id=f"together_{stage.value}_test",
        authorization_version=1,
        together_suite_id=loaded.suite_id,
        together_suite_version=loaded.suite_version,
        together_suite_sha256=content_sha256(loaded),
        robustness_profile_sha256=content_sha256(profile()),
        account_privacy_attestation_sha256=content_sha256(
            account_attestation(loaded)
        ),
        catalog_preflight_receipt_sha256=content_sha256(
            catalog_receipt(loaded)
        ),
        token_readiness_receipt_sha256=content_sha256(
            exact
        ),
        headroom_policy_sha256=content_sha256(policy),
        capability_preflight_receipt_sha256=(
            content_sha256(capability_receipt)
            if capability_receipt is not None
            else None
        ),
        stage=stage,
        budget_segment=budget_segment,
        authorized_candidate_ids=sorted(
            item.candidate.candidate_id for item in loaded.candidates
        ),
        authorized_roles=sorted(list(LLMRole), key=lambda item: item.value),
        approved_max_spend_microusd=(
            profile().budget_policy.segment_caps_microusd[budget_segment]
        ),
        approved_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def prepared_request(
    loaded: Phase4TogetherSuite,
    *,
    role: LLMRole = LLMRole.DIRECT_READOUT,
    call_id: str | None = None,
    created_at: datetime | None = None,
    interviewer_tools: list[dict[str, JsonValue]] | None = None,
    response_schema_version: int = 1,
):
    artifact = loaded.candidates[1]
    role_contract = {
        item.role: item for item in loaded.shared_role_contracts
    }[role]
    tools = []
    if role is LLMRole.INTERVIEWER:
        tools = (
            interviewer_tools
            if interviewer_tools is not None
            else [
                {
                    "name": "read_evidence_coverage",
                    "description": (
                        "Read aggregate confirmed-evidence coverage."
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                }
            ]
        )
    prompt_payload = {"system": role_contract.prompt_text}
    input_payload = {"public_case": "case_one"}
    schema = OUTPUT_ADAPTER.json_schema(mode="validation")
    attestation = build_public_development_attestation(
        attestation_id=f"together_{role.value}_privacy_test",
        prompt_payload=prompt_payload,
        input_payload=input_payload,
        response_json_schema=schema,
        tool_definitions=tools,
    )
    return prepare_provider_request(
        profile(),
        artifact.candidate,
        artifact.price_card,
        call_id=call_id or f"together_{role.value}_call_test",
        role=role,
        prompt_id=role_contract.prompt_id,
        prompt_version=role_contract.prompt_version,
        prompt_payload=prompt_payload,
        input_payload=input_payload,
        response_schema_id="demo_output",
        response_schema_version=response_schema_version,
        response_adapter=OUTPUT_ADAPTER,
        privacy_attestation=attestation,
        request_seed=42,
        provider_seed_parameter_sent=True,
        temperature=0.0,
        input_token_upper_bound=100,
        output_token_upper_bound=20,
        created_at=created_at or NOW + timedelta(minutes=1),
        tool_definitions=tools,
    )


def prepared_selector_interviewer_request(
    loaded: Phase4TogetherSuite,
    question: VettedQuestionCandidate,
):
    artifact = loaded.candidates[1]
    role_contract = next(
        item
        for item in loaded.shared_role_contracts
        if item.role is LLMRole.INTERVIEWER
    )
    prompt_payload = {
        "record_version": "phase4_together_qualification_prompt.v1",
        "role": LLMRole.INTERVIEWER.value,
        "instructions": role_contract.prompt_text,
        "canonical_prompt_id": role_contract.prompt_id,
        "canonical_prompt_sha256": role_contract.prompt_sha256,
        "variant_id": "canonical",
    }
    input_payload = {
        "record_version": "phase4_public_selector_integration_input.v1",
        "target_packet_visible": False,
        "provider_response_conformance": {
            "contract_version": 1,
            "expected_vetted_question": question.model_dump(mode="json"),
        },
    }
    response_contract = provider_response_adapter_for_role(
        LLMRole.INTERVIEWER,
        response_schema_version=3,
        input_payload=input_payload,
        bind_request_semantics=True,
    )
    tools = tool_definitions_for_role(LLMRole.INTERVIEWER)
    privacy_attestation = build_public_development_attestation(
        attestation_id="together_interviewer_selector_privacy_test",
        prompt_payload=prompt_payload,
        input_payload=input_payload,
        response_json_schema=response_contract.json_schema(mode="validation"),
        tool_definitions=tools,
    )
    return prepare_provider_request(
        profile(),
        artifact.candidate,
        artifact.price_card,
        call_id="together_interviewer_selector_call_test",
        role=LLMRole.INTERVIEWER,
        prompt_id=role_contract.prompt_id,
        prompt_version=role_contract.prompt_version,
        prompt_payload=prompt_payload,
        input_payload=input_payload,
        response_schema_id=role_contract.response_schema_id,
        response_schema_version=role_contract.response_schema_version,
        response_adapter=response_contract,
        privacy_attestation=privacy_attestation,
        request_seed=42,
        provider_seed_parameter_sent=True,
        temperature=0.0,
        input_token_upper_bound=1_000,
        output_token_upper_bound=100,
        created_at=NOW + timedelta(minutes=1),
        tool_definitions=tools,
    )


def transport(
    loaded: Phase4TogetherSuite,
    handler,
    *,
    tool_executor=None,
    input_token_count: int = 10,
    budget_segment: BudgetSegment = BudgetSegment.QUALIFICATION,
    clock_time: datetime | None = None,
    max_tool_rounds: int = 1,
) -> TogetherHTTPTransport:
    readiness = token_readiness(loaded)

    class FixedTokenCounter:
        def count_payload(self, candidate_id, payload):
            projection = {
                item.candidate_id: item
                for item in readiness.candidate_projections
            }[candidate_id]
            candidate = {
                item.candidate.candidate_id: item.candidate
                for item in loaded.candidates
            }[candidate_id]
            return TogetherPayloadTokenCount(
                candidate_id=candidate_id,
                candidate_sha256=content_sha256(candidate),
                tokenizer_id=projection.tokenizer_id,
                tokenizer_version=projection.tokenizer_version,
                tokenizer_artifact_sha256=(
                    projection.tokenizer_artifact_sha256
                ),
                payload_sha256=content_sha256(payload),
                input_token_count=input_token_count,
            )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return TogetherHTTPTransport(
        loaded,
        profile(),
        catalog_bundle(loaded),
        readiness,
        headroom_policy(),
        live_authorization(loaded, budget_segment=budget_segment),
        SecretStr("test_secret_that_never_persists"),
        client=client,
        token_counter=FixedTokenCounter(),
        tool_executor=tool_executor,
        now=NOW + timedelta(minutes=1),
        max_tool_rounds=max_tool_rounds,
        clock=lambda: clock_time or NOW + timedelta(minutes=2),
    )


def chat_response(
    *,
    content: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    tool_calls: list[object] | None = None,
) -> dict[str, object]:
    return {
        "id": f"request_{prompt_tokens}_{completion_tokens}",
        "choices": [
            {
                "index": 0,
                "seed": 42,
                "finish_reason": "tool_calls" if tool_calls else "stop",
                "message": {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": tool_calls or [],
                },
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def run_selector_interviewer(
    *,
    selected_question_id: str | None = None,
):
    loaded = load_together_suite(SUITE_V5_PATH)
    assert loaded.suite_version == 5
    item_ids = ["public_selector_item_b", "public_selector_item_a"]
    question = build_public_capability_question(item_ids)
    request = prepared_selector_interviewer_request(loaded, question)
    assert request.binding.response_schema_version == 3
    assert request.response_validator is not None
    assert request.response_validator.validator_version == 2
    calls = 0

    def handler(http_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        sent = json.loads(http_request.content)
        if calls == 1:
            assert sent["tool_choice"] == "required"
            assert "response_format" not in sent
            return httpx.Response(
                200,
                json=chat_response(
                    content=None,
                    prompt_tokens=5,
                    completion_tokens=2,
                    tool_calls=[
                        {
                            "id": "selector_tool_call",
                            "type": "function",
                            "function": {
                                "name": "read_candidate_question_scores",
                                "arguments": '{"limit":1}',
                            },
                        }
                    ],
                ),
            )
        assert calls == 2
        assert sent["messages"][-1]["name"] == (
            "read_candidate_question_scores"
        )
        tool_result = json.loads(sent["messages"][-1]["content"])
        assert tool_result == ReadCandidateQuestionScoresResult(
            candidates=[question],
            model_version="capability_preflight_v1",
        ).model_dump(mode="json")
        assert "tools" not in sent
        assert sent["response_format"]["type"] == "json_schema"
        return httpx.Response(
            200,
            json=chat_response(
                content=json.dumps(
                    {
                        "record_version": (
                            "phase4_ask_vetted_question_selector.v1"
                        ),
                        "action": "ask_vetted_question",
                        "selected_question_id": (
                            selected_question_id or question.question_id
                        ),
                        "rendering_mode": "canonical_vetted",
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                prompt_tokens=8,
                completion_tokens=3,
            ),
        )

    runtime = ProviderBudgetRuntime(
        profile(),
        ledger_id="together_selector_ledger",
        journal_id="together_selector_journal",
    )
    execution = runtime.execute(
        request,
        loaded.candidates[1].price_card,
        None,
        transport(
            loaded,
            handler,
            tool_executor=TogetherInterviewerToolExecutor(
                CapabilityInterviewerTools(item_ids)
            ),
        ),
        segment=BudgetSegment.QUALIFICATION,
    )
    expected_context = {
        "record_version": "phase4_interviewer_tool_result_context.v1",
        "candidate_question_results": [
            ReadCandidateQuestionScoresResult(
                candidates=[question],
                model_version="capability_preflight_v1",
            ).model_dump(mode="json")
        ],
    }
    return loaded, runtime, execution, question, expected_context, calls


def test_local_api_key_loader_never_serializes_secret(tmp_path: Path) -> None:
    secret_value = "together_secret_for_local_test_only"
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        f"TOGETHER_API_KEY={secret_value}\n",
        encoding="utf-8",
    )

    secret = load_together_api_key(environment={}, local_env_file=env_file)

    assert secret.get_secret_value() == secret_value
    assert secret_value not in repr(secret)
    assert secret_value not in json.dumps(secret.__repr__())


def test_catalog_preflight_is_one_shot_zero_spend_and_secret_free() -> None:
    loaded = suite()
    observed_auth = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_auth.append(request.headers["Authorization"])
        assert request.method == "GET"
        assert request.url.path == "/v1/models"
        return httpx.Response(200, json=live_model_payload(loaded))

    secret_value = "test_secret_that_never_persists"
    client = TogetherCatalogPreflightClient(
        loaded,
        account_attestation(loaded),
        public_sources(loaded),
        catalog_authorization(loaded),
        SecretStr(secret_value),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        now=NOW + timedelta(minutes=1),
        clock=lambda: NOW + timedelta(minutes=2),
    )

    receipt = client.run(
        receipt_id="together_catalog_live_test",
    )

    assert len(receipt.candidate_checks) == 3
    assert receipt.provider_spend_microusd == 0
    assert secret_value not in receipt.model_dump_json()
    assert observed_auth == [f"Bearer {secret_value}"]
    with pytest.raises(ValueError, match="authorization is spent"):
        client.run(
            receipt_id="together_catalog_live_test_again",
        )


def test_public_source_reverification_never_sends_provider_key() -> None:
    loaded = suite()
    observed_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert "Authorization" not in request.headers
        observed_urls.append(str(request.url))
        return httpx.Response(200, content=str(request.url).encode())

    receipt = fetch_public_source_reverification(
        loaded,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        receipt_id="together_public_source_live_test",
        checked_at=NOW,
    )

    assert observed_urls == sorted(observed_urls)
    assert len(receipt.source_checks) == len(observed_urls)
    assert len(observed_urls) >= 7


def test_catalog_preflight_rejects_live_price_drift() -> None:
    loaded = suite()
    payload = live_model_payload(loaded)
    payload[0]["pricing"]["input"] = "99.0"

    with pytest.raises(ValueError, match="metadata differs"):
        build_catalog_preflight_receipt(
            loaded,
            catalog_authorization(loaded),
            payload,
            receipt_id="together_catalog_drift_test",
            checked_at=NOW,
        )


def test_catalog_preflight_ignores_incomplete_unrelated_models() -> None:
    loaded = suite()
    payload = live_model_payload(loaded)
    payload.append(
        {
            "id": "unrelated/catalog-model",
            "pricing": {"input": "0.0", "output": "0.0"},
        }
    )

    receipt = build_catalog_preflight_receipt(
        loaded,
        catalog_authorization(loaded),
        payload,
        receipt_id="together_catalog_unrelated_model_test",
        checked_at=NOW,
    )

    assert len(receipt.candidate_checks) == len(loaded.candidates)


def test_catalog_preflight_records_distinct_live_context_window() -> None:
    loaded = suite()
    payload = live_model_payload(loaded)
    payload[0]["context_length"] = 1_048_575

    receipt = build_catalog_preflight_receipt(
        loaded,
        catalog_authorization(loaded),
        payload,
        receipt_id="together_catalog_live_context_test",
        checked_at=NOW,
    )

    check = next(
        item
        for item in receipt.candidate_checks
        if item.serving_model_id == payload[0]["id"]
    )
    assert check.advertised_context_window_tokens == 512_000
    assert check.live_context_window_tokens == 1_048_575
    assert check.required_context_window_tokens == 16_000
    mismatch_count, maximum_difference_ppm = _context_window_diagnostics(
        receipt
    )
    assert mismatch_count == 1
    assert maximum_difference_ppm > 1_000_000


def test_catalog_preflight_rejects_insufficient_live_context() -> None:
    loaded = suite()
    payload = live_model_payload(loaded)
    payload[0]["context_length"] = 8_999

    with pytest.raises(ValueError, match="cannot fit the study workload"):
        build_catalog_preflight_receipt(
            loaded,
            catalog_authorization(loaded),
            payload,
            receipt_id="together_catalog_small_context_test",
            checked_at=NOW,
        )


def test_catalog_preflight_rejects_incomplete_candidate_model() -> None:
    loaded = suite()
    payload = live_model_payload(loaded)
    del payload[0]["context_length"]

    with pytest.raises(ValidationError):
        build_catalog_preflight_receipt(
            loaded,
            catalog_authorization(loaded),
            payload,
            receipt_id="together_catalog_incomplete_candidate_test",
            checked_at=NOW,
        )


def test_paid_transport_rejects_missing_exact_headroom_before_http() -> None:
    loaded = suite()
    exact = token_readiness(loaded)
    strict_headroom = headroom_policy().model_copy(
        update={"held_out_minimum_headroom_microusd": 12_999_999}
    )
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500, json={})

    with pytest.raises(ValueError, match="lacks headroom"):
        TogetherHTTPTransport(
            loaded,
            profile(),
            catalog_bundle(loaded),
            exact,
            strict_headroom,
            live_authorization(
                loaded,
                projection=exact,
                headroom=strict_headroom,
            ),
            SecretStr("test_secret_that_never_persists"),
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            token_counter=type(
                "UnusedTokenCounter",
                (),
                {"count_payload": lambda self, candidate_id, payload: None},
            )(),
            now=NOW + timedelta(minutes=1),
            clock=lambda: NOW + timedelta(minutes=2),
        )
    assert called is False


def test_runtime_checks_transport_gate_before_budget_reservation() -> None:
    loaded = suite()
    request = prepared_request(loaded)
    artifact = loaded.candidates[1]

    class RejectingTransport:
        invoked = False

        def validate_execution(self, request, *, segment):
            del request, segment
            raise ValueError("live authorization missing")

        def invoke(self, request):
            del request
            self.invoked = True
            raise AssertionError("transport must not run")

    rejecting = RejectingTransport()
    runtime = ProviderBudgetRuntime(
        profile(),
        ledger_id="together_gate_ledger",
        journal_id="together_gate_journal",
    )

    with pytest.raises(ValueError, match="live authorization missing"):
        runtime.execute(
            request,
            artifact.price_card,
            OUTPUT_ADAPTER,
            rejecting,
            segment=BudgetSegment.QUALIFICATION,
        )

    assert runtime.ledger_snapshot().authorizations == []
    assert rejecting.invoked is False


def test_exact_token_gate_rejects_before_reservation_or_http() -> None:
    loaded = suite()
    request = prepared_request(loaded)
    artifact = loaded.candidates[1]
    called = False

    def handler(http_request: httpx.Request) -> httpx.Response:
        nonlocal called
        del http_request
        called = True
        return httpx.Response(500, json={})

    runtime = ProviderBudgetRuntime(
        profile(),
        ledger_id="together_token_gate_ledger",
        journal_id="together_token_gate_journal",
    )

    with pytest.raises(ValueError, match="exact input count exceeds"):
        runtime.execute(
            request,
            artifact.price_card,
            OUTPUT_ADAPTER,
            transport(loaded, handler, input_token_count=101),
            segment=BudgetSegment.QUALIFICATION,
        )

    assert runtime.ledger_snapshot().authorizations == []
    assert called is False


def test_live_transport_integrates_with_budget_runtime() -> None:
    loaded = suite()
    request = prepared_request(loaded)
    artifact = loaded.candidates[1]

    def handler(http_request: httpx.Request) -> httpx.Response:
        assert http_request.url.path == "/v1/chat/completions"
        return httpx.Response(
            200,
            json=chat_response(
                content='{"choice":"yes","confidence":0.8}',
                prompt_tokens=5,
                completion_tokens=3,
            ),
        )

    runtime = ProviderBudgetRuntime(
        profile(),
        ledger_id="together_live_ledger",
        journal_id="together_live_journal",
    )
    execution = runtime.execute(
        request,
        artifact.price_card,
        OUTPUT_ADAPTER,
        transport(loaded, handler),
        segment=BudgetSegment.QUALIFICATION,
    )

    assert execution.output == DemoOutput(choice="yes", confidence=0.8)
    assert execution.finalization.outcome is ProviderCallOutcome.SUCCESS
    ledger = runtime.ledger_snapshot()
    assert ledger.calls[0].input_tokens == 5
    assert ledger.calls[0].output_tokens == 3


def test_live_transport_executes_bounded_interviewer_tool_loop() -> None:
    loaded = suite()
    request = prepared_request(loaded, role=LLMRole.INTERVIEWER)
    calls = 0

    class ToolExecutor:
        def execute(self, name, arguments):
            assert name == "read_evidence_coverage"
            assert arguments == {}
            return {"evidence_count": 3}

    def handler(http_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        sent = json.loads(http_request.content)
        if calls == 1:
            assert "response_format" not in sent
            assert sent["tool_choice"] == "required"
            return httpx.Response(
                200,
                json=chat_response(
                    content=None,
                    prompt_tokens=5,
                    completion_tokens=2,
                    tool_calls=[
                        {
                            "id": "tool_call_one",
                            "type": "function",
                            "function": {
                                "name": "read_evidence_coverage",
                                "arguments": "{}",
                            },
                        }
                    ],
                ),
            )
        assert sent["messages"][-1] == {
            "role": "tool",
            "tool_call_id": "tool_call_one",
            "name": "read_evidence_coverage",
            "content": '{"evidence_count":3}',
        }
        assert "tools" not in sent
        assert "tool_choice" not in sent
        assert sent["response_format"]["type"] == "json_schema"
        return httpx.Response(
            200,
            json=chat_response(
                content='{"choice":"pause","confidence":0.6}',
                prompt_tokens=8,
                completion_tokens=3,
            ),
        )

    result = transport(
        loaded,
        handler,
        tool_executor=ToolExecutor(),
    ).invoke(request)

    assert result.outcome is ProviderCallOutcome.SUCCESS
    assert result.output_payload == {"choice": "pause", "confidence": 0.6}
    assert result.input_tokens == 13
    assert result.output_tokens == 5
    assert result.tool_call_count == 1
    assert result.tool_call_failure_count == 0
    assert result.record_version == "phase4_provider_transport_result.v1"
    assert result.response_validation_context is None
    assert result.response_validation_context_sha256 is None
    assert calls == 2


def test_interviewer_retains_exact_candidate_tool_results_ephemerally() -> None:
    loaded = suite()
    candidate_tool = {
        "name": "read_candidate_question_scores",
        "description": "Read exact vetted candidate questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
            },
            "additionalProperties": False,
        },
    }
    request = prepared_request(
        loaded,
        role=LLMRole.INTERVIEWER,
        interviewer_tools=[candidate_tool],
        response_schema_version=3,
    )
    marker = "exact_candidate_context_must_remain_ephemeral"
    typed_results = [
        ReadCandidateQuestionScoresResult(
            candidates=[],
            model_version=marker,
        ),
        ReadCandidateQuestionScoresResult(
            candidates=[],
            model_version=f"{marker}_second",
        ),
    ]
    exact_results: list[JsonValue] = [
        item.model_dump(mode="json") for item in typed_results
    ]
    observed_tool_limits: list[int] = []
    provider_round = 0

    class InterviewerTools:
        def read_candidate_question_scores(self, request):
            observed_tool_limits.append(request.limit)
            return typed_results[len(observed_tool_limits) - 1]

        def read_posterior_uncertainty(self, request):
            raise AssertionError(request)

        def read_evidence_coverage(self, request):
            raise AssertionError(request)

        def read_evidence_conflicts(self, request):
            raise AssertionError(request)

    def handler(http_request: httpx.Request) -> httpx.Response:
        nonlocal provider_round
        provider_round += 1
        sent = json.loads(http_request.content)
        if provider_round == 1:
            return httpx.Response(
                200,
                json=chat_response(
                    content=None,
                    prompt_tokens=5,
                    completion_tokens=2,
                    tool_calls=[
                        {
                            "id": "candidate_tool_call_one",
                            "type": "function",
                            "function": {
                                "name": "read_candidate_question_scores",
                                "arguments": '{"limit":1}',
                            },
                        },
                        {
                            "id": "candidate_tool_call_two",
                            "type": "function",
                            "function": {
                                "name": "read_candidate_question_scores",
                                "arguments": '{"limit":2}',
                            },
                        },
                    ],
                ),
            )
        assert sent["messages"][-2]["content"] == json.dumps(
            exact_results[0],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        assert sent["messages"][-1]["content"] == json.dumps(
            exact_results[1],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return httpx.Response(
            200,
            json=chat_response(
                content='{"choice":"pause","confidence":0.6}',
                prompt_tokens=8,
                completion_tokens=3,
            ),
        )

    result = transport(
        loaded,
        handler,
        tool_executor=TogetherInterviewerToolExecutor(InterviewerTools()),
    ).invoke(request)

    expected_context = {
        "record_version": "phase4_interviewer_tool_result_context.v1",
        "candidate_question_results": exact_results,
    }
    assert provider_round == 2
    assert observed_tool_limits == [1, 2]
    assert result.outcome is ProviderCallOutcome.SUCCESS
    assert result.tool_call_count == 2
    assert result.record_version == "phase4_provider_transport_result.v2"
    assert result.response_validation_context == expected_context
    assert result.response_validation_context_sha256 == content_sha256(
        expected_context
    )
    persisted = result.model_dump(mode="json")
    assert "response_validation_context" not in persisted
    assert persisted["response_validation_context_sha256"] == content_sha256(
        expected_context
    )
    assert marker not in json.dumps(persisted, sort_keys=True)
    assert marker not in repr(result)


def test_selector_interviewer_hydrates_and_audits_through_live_runtime() -> None:
    (
        loaded,
        runtime,
        execution,
        question,
        expected_context,
        calls,
    ) = run_selector_interviewer()
    expected = AskVettedQuestionDecision(
        question=question,
        rendering_mode="canonical_vetted",
    )

    assert calls == 2
    assert isinstance(execution.output, AskVettedQuestionDecision)
    assert execution.output.model_dump_json() == expected.model_dump_json()
    assert execution.output.model_dump(mode="json") == expected.model_dump(
        mode="json"
    )
    assert execution.finalization.outcome is ProviderCallOutcome.SUCCESS
    assert execution.finalization.response_sha256 == content_sha256(
        expected.model_dump(mode="json")
    )
    assert execution.finalization.record_version == (
        "phase4_provider_call_finalization.v2"
    )
    assert execution.finalization.response_validation_context_sha256 == (
        content_sha256(expected_context)
    )
    artifact = loaded.candidates[1]
    runtime.audit([artifact.candidate], [artifact.price_card])

    persisted = json.dumps(
        {
            "ledger": runtime.ledger_snapshot().model_dump(mode="json"),
            "journal": runtime.journal_snapshot().model_dump(mode="json"),
        },
        sort_keys=True,
    )
    raw_context = json.dumps(expected_context, sort_keys=True)
    assert raw_context not in persisted
    assert question.prompt not in persisted
    assert question.question_id not in persisted
    assert content_sha256(expected_context) in persisted


def test_selector_interviewer_rejects_unreturned_selector_without_leak() -> None:
    planted_id = "planted_unreturned_question_secret"
    (
        loaded,
        runtime,
        execution,
        question,
        expected_context,
        calls,
    ) = run_selector_interviewer(
        selected_question_id=planted_id,
    )

    assert calls == 2
    assert execution.output is None
    assert execution.finalization.outcome is ProviderCallOutcome.INVALID_OUTPUT
    assert execution.finalization.response_sha256 is None
    assert execution.finalization.response_validation_context_sha256 == (
        content_sha256(expected_context)
    )
    assert execution.validation_diagnostic is not None
    assert execution.validation_diagnostic.error_count == 1
    assert execution.validation_diagnostic.issues[0].model_dump(mode="json") == {
        "path": ["selected_question_id"],
        "error_type": "question_selector_not_returned",
    }
    assert runtime.ledger_snapshot().calls[0].billed_cost_microusd > 0
    artifact = loaded.candidates[1]
    runtime.audit([artifact.candidate], [artifact.price_card])

    persisted = json.dumps(
        {
            "diagnostic": execution.validation_diagnostic.model_dump(
                mode="json"
            ),
            "ledger": runtime.ledger_snapshot().model_dump(mode="json"),
            "journal": runtime.journal_snapshot().model_dump(mode="json"),
        },
        sort_keys=True,
    )
    assert planted_id not in persisted
    assert question.prompt not in persisted
    assert question.question_id not in persisted
    assert content_sha256(expected_context) in persisted


def test_non_interviewer_transport_result_has_no_validation_context() -> None:
    loaded = suite()
    request = prepared_request(loaded)

    result = transport(
        loaded,
        lambda request: httpx.Response(
            200,
            json=chat_response(
                content='{"choice":"yes","confidence":0.8}',
                prompt_tokens=5,
                completion_tokens=3,
            ),
        ),
    ).invoke(request)

    assert result.record_version == "phase4_provider_transport_result.v1"
    assert result.response_validation_context is None
    assert result.response_validation_context_sha256 is None
    persisted = result.model_dump(mode="json")
    assert "response_validation_context" not in persisted
    assert "response_validation_context_sha256" not in persisted


def test_v3_interviewer_fails_when_required_tool_call_is_missing() -> None:
    loaded = suite()
    request = prepared_request(loaded, role=LLMRole.INTERVIEWER)

    result = transport(
        loaded,
        lambda request: httpx.Response(
            200,
            json=chat_response(
                content='{"choice":"pause","confidence":0.6}',
                prompt_tokens=5,
                completion_tokens=3,
            ),
        ),
    ).invoke(request)

    assert result.outcome is ProviderCallOutcome.TRANSPORT_ERROR
    assert result.failure_code == "together_required_tool_call_missing"
    assert result.tool_call_count == 0


def test_live_transport_rejects_a_tool_round_limit_not_in_readiness() -> None:
    loaded = suite()

    with pytest.raises(
        ValueError,
        match="max tool rounds differ from readiness",
    ):
        transport(
            loaded,
            lambda request: httpx.Response(500),
            max_tool_rounds=2,
        )


def test_ambiguous_sent_response_preserves_outstanding_authorization() -> None:
    loaded = suite()
    request = prepared_request(loaded)
    artifact = loaded.candidates[1]

    def handler(http_request: httpx.Request) -> httpx.Response:
        del http_request
        return httpx.Response(200, content=b"not-json")

    runtime = ProviderBudgetRuntime(
        profile(),
        ledger_id="together_ambiguous_ledger",
        journal_id="together_ambiguous_journal",
    )

    with pytest.raises(TogetherAmbiguousDeliveryError):
        runtime.execute(
            request,
            artifact.price_card,
            OUTPUT_ADAPTER,
            transport(loaded, handler),
            segment=BudgetSegment.QUALIFICATION,
        )

    ledger = runtime.ledger_snapshot()
    assert len(ledger.authorizations) == 1
    assert ledger.calls == []


@pytest.mark.parametrize("status_code", [101, 429, 500, 503])
def test_http_error_closes_runtime_reservation(status_code: int) -> None:
    loaded = suite()
    request = prepared_request(loaded)
    artifact = loaded.candidates[1]

    def handler(http_request: httpx.Request) -> httpx.Response:
        del http_request
        return httpx.Response(status_code, json={"error": "unavailable"})

    runtime = ProviderBudgetRuntime(
        profile(),
        ledger_id=f"together_http_{status_code}_ledger",
        journal_id=f"together_http_{status_code}_journal",
    )
    execution = runtime.execute(
        request,
        artifact.price_card,
        OUTPUT_ADAPTER,
        transport(loaded, handler),
        segment=BudgetSegment.QUALIFICATION,
    )

    assert execution.output is None
    assert execution.finalization.outcome is ProviderCallOutcome.PROVIDER_ERROR
    assert execution.finalization.failure_code == f"together_http_{status_code}"
    ledger = runtime.ledger_snapshot()
    assert len(ledger.authorizations) == 1
    assert len(ledger.calls) == 1
    assert ledger.calls[0].input_tokens == 0
    assert ledger.calls[0].output_tokens == 0
    runtime.audit([artifact.candidate], [artifact.price_card])


def test_closed_http_error_can_retry_from_retry_reserve() -> None:
    loaded = suite()
    artifact = loaded.candidates[1]
    first = prepared_request(
        loaded,
        call_id="together_retry_source",
        created_at=NOW + timedelta(minutes=1),
    )
    retry = prepared_request(
        loaded,
        call_id="together_retry_attempt",
        created_at=NOW + timedelta(minutes=3),
    )
    runtime = ProviderBudgetRuntime(
        profile(),
        ledger_id="together_retry_ledger",
        journal_id="together_retry_journal",
    )

    failed = runtime.execute(
        first,
        artifact.price_card,
        OUTPUT_ADAPTER,
        transport(
            loaded,
            lambda request: httpx.Response(
                429,
                json={"error": "rate_limited"},
            ),
        ),
        segment=BudgetSegment.QUALIFICATION,
    )
    succeeded = runtime.execute(
        retry,
        artifact.price_card,
        OUTPUT_ADAPTER,
        transport(
            loaded,
            lambda request: httpx.Response(
                200,
                json=chat_response(
                    content='{"choice":"yes","confidence":0.8}',
                    prompt_tokens=5,
                    completion_tokens=3,
                ),
            ),
            budget_segment=BudgetSegment.RETRY_RESERVE,
            clock_time=NOW + timedelta(minutes=4),
        ),
        segment=BudgetSegment.RETRY_RESERVE,
        retry_of_call_id="together_retry_source",
    )

    assert failed.finalization.outcome is ProviderCallOutcome.PROVIDER_ERROR
    assert succeeded.finalization.outcome is ProviderCallOutcome.SUCCESS
    ledger = runtime.ledger_snapshot()
    assert [item.segment for item in ledger.calls] == [
        BudgetSegment.QUALIFICATION,
        BudgetSegment.RETRY_RESERVE,
    ]
    assert ledger.calls[1].retry_of_call_id == "together_retry_source"
    runtime.audit([artifact.candidate], [artifact.price_card])


def test_live_authorization_binds_exact_segment_cap() -> None:
    loaded = suite()
    retry_authorization = live_authorization(
        loaded,
        budget_segment=BudgetSegment.RETRY_RESERVE,
    )
    invalid = retry_authorization.model_copy(
        update={"approved_max_spend_microusd": 4_000_000}
    )

    with pytest.raises(ValueError, match="segment cap differs"):
        TogetherHTTPTransport(
            loaded,
            profile(),
            catalog_bundle(loaded),
            token_readiness(loaded),
            headroom_policy(),
            invalid,
            SecretStr("test_secret_that_never_persists"),
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(500, json={})
                )
            ),
            token_counter=type(
                "UnusedTokenCounter",
                (),
                {"count_payload": lambda self, candidate_id, payload: None},
            )(),
            now=NOW + timedelta(minutes=1),
        )


def test_live_authorization_excludes_held_out_segment() -> None:
    loaded = suite()
    payload = live_authorization(loaded).model_dump(mode="json")
    payload["budget_segment"] = BudgetSegment.HELD_OUT_STUDY.value
    payload["approved_max_spend_microusd"] = 13_000_000

    with pytest.raises(ValidationError):
        TogetherLiveAuthorization.model_validate(payload)


def test_live_authorization_v1_round_trip_omits_exact_request_extension() -> None:
    original = live_authorization(suite())
    payload = original.model_dump(mode="json")

    assert "authorized_requests" not in payload
    assert TogetherLiveAuthorization.model_validate(payload) == original


def test_exact_live_authorization_rejects_any_other_request() -> None:
    loaded = suite()
    request = prepared_request(
        loaded,
        call_id="exact_retry_call",
        created_at=NOW + timedelta(minutes=1),
    )
    artifact = loaded.candidates[1]
    maximum = price_provider_tokens(
        artifact.price_card,
        input_tokens=request.binding.input_token_upper_bound,
        output_tokens=request.binding.output_token_upper_bound,
    )
    exact_request = TogetherAuthorizedProviderRequest(
        call_id=request.binding.call_id,
        model_candidate_id=request.binding.model_candidate_id,
        role=request.binding.role,
        request_content_sha256=provider_request_content_sha256(
            request.binding
        ),
        authorized_max_cost_microusd=maximum,
    )
    readiness = token_readiness(loaded)
    policy = headroom_policy()
    authorization = TogetherLiveAuthorization(
        record_version="phase4_together_live_authorization.v2",
        authorization_id="together_exact_retry_test",
        authorization_version=2,
        together_suite_id=loaded.suite_id,
        together_suite_version=loaded.suite_version,
        together_suite_sha256=content_sha256(loaded),
        robustness_profile_sha256=content_sha256(profile()),
        account_privacy_attestation_sha256=content_sha256(
            account_attestation(loaded)
        ),
        catalog_preflight_receipt_sha256=content_sha256(
            catalog_receipt(loaded)
        ),
        token_readiness_receipt_sha256=content_sha256(readiness),
        headroom_policy_sha256=content_sha256(policy),
        stage=TogetherPaidStage.CAPABILITY_PREFLIGHT,
        budget_segment=BudgetSegment.RETRY_RESERVE,
        authorized_candidate_ids=[request.binding.model_candidate_id],
        authorized_roles=[request.binding.role],
        authorized_requests=[exact_request],
        approved_max_spend_microusd=maximum,
        approved_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )

    class FixedTokenCounter:
        def count_payload(self, candidate_id, payload):
            projection = {
                item.candidate_id: item
                for item in readiness.candidate_projections
            }[candidate_id]
            candidate = {
                item.candidate.candidate_id: item.candidate
                for item in loaded.candidates
            }[candidate_id]
            return TogetherPayloadTokenCount(
                candidate_id=candidate_id,
                candidate_sha256=content_sha256(candidate),
                tokenizer_id=projection.tokenizer_id,
                tokenizer_version=projection.tokenizer_version,
                tokenizer_artifact_sha256=(
                    projection.tokenizer_artifact_sha256
                ),
                payload_sha256=content_sha256(payload),
                input_token_count=10,
            )

    exact_transport = TogetherHTTPTransport(
        loaded,
        profile(),
        catalog_bundle(loaded),
        readiness,
        policy,
        authorization,
        SecretStr("test_secret_that_never_persists"),
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda http_request: httpx.Response(500, json={})
            )
        ),
        token_counter=FixedTokenCounter(),
        now=NOW + timedelta(minutes=1),
        clock=lambda: NOW + timedelta(minutes=2),
    )
    exact_transport.validate_execution(
        request,
        segment=BudgetSegment.RETRY_RESERVE,
    )
    wrong_scope = authorization.model_dump(mode="json")
    wrong_scope["budget_segment"] = BudgetSegment.QUALIFICATION.value
    with pytest.raises(ValidationError, match="retry-diagnostic-only"):
        TogetherLiveAuthorization.model_validate(wrong_scope)
    wrong_call = request.model_copy(
        update={
            "binding": request.binding.model_copy(
                update={"call_id": "another_retry_call"}
            )
        }
    )
    with pytest.raises(ValueError, match="not exactly authorized"):
        exact_transport.validate_execution(
            wrong_call,
            segment=BudgetSegment.RETRY_RESERVE,
        )

    wrong_content = request.model_copy(
        update={
            "binding": request.binding.model_copy(
                update={"temperature": 0.25}
            )
        }
    )
    with pytest.raises(ValueError, match="exact request binding differs"):
        exact_transport.validate_execution(
            wrong_content,
            segment=BudgetSegment.RETRY_RESERVE,
        )


def test_followup_http_error_retains_prior_round_usage() -> None:
    loaded = suite()
    request = prepared_request(loaded, role=LLMRole.INTERVIEWER)
    calls = 0

    class ToolExecutor:
        def execute(self, name, arguments):
            del name, arguments
            return {"evidence_count": 3}

    def handler(http_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        del http_request
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                json=chat_response(
                    content=None,
                    prompt_tokens=5,
                    completion_tokens=2,
                    tool_calls=[
                        {
                            "id": "tool_call_one",
                            "type": "function",
                            "function": {
                                "name": "read_evidence_coverage",
                                "arguments": "{}",
                            },
                        }
                    ],
                ),
            )
        return httpx.Response(429, json={"error": "rate_limited"})

    result = transport(
        loaded,
        handler,
        tool_executor=ToolExecutor(),
    ).invoke(request)

    assert result.outcome is ProviderCallOutcome.PROVIDER_ERROR
    assert result.input_tokens == 5
    assert result.output_tokens == 2
    assert result.tool_call_count == 1
    assert result.failure_code == "together_http_429"


def test_live_preflight_cli_fails_before_secret_or_network_without_confirmations(
    capsys,
) -> None:
    exit_code = catalog_preflight_main(
        [
            str(SUITE_PATH),
            str(ROOT / "eval/private_runs/together/catalog.json"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "restricted details omitted" in captured.err
