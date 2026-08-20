from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from eval.contracts import ContractModel
from eval.fixture_io import content_sha256
from eval.phase4_provider import (
    build_public_development_attestation,
    prepare_provider_request,
)
from eval.phase4_robustness import LLMRole, load_phase4_robustness_profile
from eval.phase4_together import (
    Phase4TogetherSuite,
    build_default_together_suite,
    build_no_spend_report,
    build_together_chat_payload,
    load_together_suite,
    validate_request_against_role_envelope,
)
from eval.validate_phase4_together import main as validate_main

ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = (
    ROOT / "eval/fixtures/preference_eval_phase4_robustness_v1.json"
)
SUITE_PATH = ROOT / "eval/fixtures/preference_eval_phase4_together_v1.json"
NOW = datetime(2026, 8, 20, 13, 0, tzinfo=timezone.utc)


class DemoOutput(ContractModel):
    choice: str
    confidence: float


OUTPUT_ADAPTER = TypeAdapter(DemoOutput)


def profile():
    return load_phase4_robustness_profile(PROFILE_PATH)


def suite() -> Phase4TogetherSuite:
    return load_together_suite(SUITE_PATH)


def prepared_request(
    *,
    role: LLMRole = LLMRole.DIRECT_READOUT,
    input_payload: object | None = None,
    input_token_upper_bound: int = 6_000,
    provider_seed_parameter_sent: bool = True,
):
    robustness_profile = profile()
    together_suite = suite()
    artifact = together_suite.candidates[1]
    role_contract = {
        item.role: item for item in together_suite.shared_role_contracts
    }[role]
    prompt_payload = {"system": role_contract.prompt_text}
    resolved_input = input_payload or {"public_case": "case_one"}
    tools = []
    if role is LLMRole.INTERVIEWER:
        tools = [
            {
                "name": "read_evidence_coverage",
                "description": "Read aggregate evidence coverage.",
                "input_schema": {"type": "object", "properties": {}},
            }
        ]
    schema = OUTPUT_ADAPTER.json_schema(mode="validation")
    attestation = build_public_development_attestation(
        attestation_id="together_test_attestation",
        prompt_payload=prompt_payload,
        input_payload=resolved_input,
        response_json_schema=schema,
        tool_definitions=tools,
    )
    return prepare_provider_request(
        robustness_profile,
        artifact.candidate,
        artifact.price_card,
        call_id="together_test_call",
        role=role,
        prompt_id=role_contract.prompt_id,
        prompt_version=role_contract.prompt_version,
        prompt_payload=prompt_payload,
        input_payload=resolved_input,
        response_schema_id="demo_output",
        response_schema_version=1,
        response_adapter=OUTPUT_ADAPTER,
        privacy_attestation=attestation,
        request_seed=42,
        provider_seed_parameter_sent=provider_seed_parameter_sent,
        temperature=0.0,
        input_token_upper_bound=input_token_upper_bound,
        output_token_upper_bound=500,
        created_at=NOW,
        tool_definitions=tools,
    )


def test_tracked_suite_matches_deterministic_builder() -> None:
    loaded = suite()
    expected = build_default_together_suite(profile())

    assert loaded == expected
    assert content_sha256(loaded) == content_sha256(expected)
    assert len(loaded.candidates) == 3
    assert len(loaded.shared_role_contracts) == 5


def test_candidate_ids_revisions_and_prices_are_frozen() -> None:
    loaded = suite()

    assert [item.candidate.candidate_id for item in loaded.candidates] == [
        "together_glm_5_2",
        "together_gpt_oss_120b",
        "together_nemotron_3_ultra_550b_a55b",
    ]
    assert [
        item.candidate.upstream_model_revision for item in loaded.candidates
    ] == [
        "48cf76872d0f20ab526a663f7e540817afc9b9ef",
        "b5c939de8f754692c1647ca79fbf85e8c1e70f8a",
        "183968f87ae4cedce3039313cac1fd43d112c578",
    ]
    assert [
        (
            item.price_card.input_microusd_per_million_tokens,
            item.price_card.output_microusd_per_million_tokens,
        )
        for item in loaded.candidates
    ] == [
        (1_400_000, 4_400_000),
        (150_000, 600_000),
        (600_000, 3_600_000),
    ]


def test_no_spend_projection_fits_both_budget_segments() -> None:
    report = build_no_spend_report(suite(), profile())

    assert report.qualification_request_count == 456
    assert report.qualification_projected_cost_microusd == 3_422_800
    assert report.qualification_projected_headroom_microusd == 577_200
    assert report.held_out_request_count == 912
    assert report.held_out_projected_cost_microusd_by_candidate == {
        "together_glm_5_2": 12_307_200,
        "together_gpt_oss_120b": 1_432_800,
        "together_nemotron_3_ultra_550b_a55b": 6_796_800,
    }
    assert report.held_out_projected_headroom_microusd_by_candidate == {
        "together_glm_5_2": 692_800,
        "together_gpt_oss_120b": 11_567_200,
        "together_nemotron_3_ultra_550b_a55b": 6_203_200,
    }
    assert report.exact_candidate_tokenizer_projection_complete is False
    assert report.projected_headroom_gate_frozen is False
    assert report.live_authorization_ready is False
    assert report.network_call_count == 0
    assert report.spend_microusd == 0


def test_together_codec_is_deterministic_and_credential_free() -> None:
    loaded = suite()
    request = prepared_request()

    first = build_together_chat_payload(loaded, request)
    second = build_together_chat_payload(loaded, request)

    assert first == second
    assert first["model"] == "openai/gpt-oss-120b"
    assert first["seed"] == 42
    assert first["response_format"]["type"] == "json_schema"
    assert "tools" not in first
    rendered = json.dumps(first, sort_keys=True).lower()
    assert "api_key" not in rendered
    assert "authorization" not in rendered


def test_interviewer_codec_uses_standard_function_shape() -> None:
    payload = build_together_chat_payload(
        suite(),
        prepared_request(role=LLMRole.INTERVIEWER),
    )

    assert payload["tool_choice"] == "auto"
    assert payload["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "read_evidence_coverage",
                "description": "Read aggregate evidence coverage.",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]


def test_codec_omits_seed_when_binding_says_it_was_not_sent() -> None:
    request = prepared_request(provider_seed_parameter_sent=False)

    payload = build_together_chat_payload(suite(), request)

    assert "seed" not in payload


def test_request_must_fit_conservative_role_envelope() -> None:
    loaded = suite()
    request = prepared_request(input_token_upper_bound=6_001)

    with pytest.raises(
        ValueError,
        match="exceeds role input-token envelope",
    ):
        validate_request_against_role_envelope(
            loaded,
            request,
            held_out=False,
        )


def test_suite_rejects_price_drift() -> None:
    payload = suite().model_dump(mode="json")
    payload["candidates"][0]["price_card"][
        "input_microusd_per_million_tokens"
    ] += 1

    with pytest.raises(ValidationError):
        Phase4TogetherSuite.model_validate(payload)


def test_held_out_cap_error_names_public_candidate() -> None:
    high_cost_suite = suite()
    for usage in (
        high_cost_suite.workload.held_out_selected_candidate.role_usage
    ):
        usage.input_tokens_per_request *= 10

    with pytest.raises(
        ValueError,
        match="together_glm_5_2 exceeds hard cap",
    ):
        build_no_spend_report(high_cost_suite, profile())


def test_validate_cli_is_aggregate_and_zero_spend(capsys) -> None:
    exit_code = validate_main([str(SUITE_PATH), str(PROFILE_PATH)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["candidate_count"] == 3
    assert payload["network_call_count"] == 0
    assert payload["spend_microusd"] == 0
    assert "prompt_text" not in captured.out
