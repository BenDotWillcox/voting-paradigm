from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from eval.contracts import ContractModel
from eval.fixture_io import content_sha256
from eval.phase4_provider import (
    ProviderResponseContract,
    build_public_development_attestation,
    prepare_provider_request,
)
from eval.phase4_robustness import LLMRole, load_phase4_robustness_profile
from eval.phase4_together import (
    EVIDENCE_EXTRACTOR_PROMPT_V1,
    EVIDENCE_EXTRACTOR_PROMPT_V2,
    Phase4TogetherSuite,
    build_default_together_suite,
    build_no_spend_report,
    build_together_chat_payload,
    build_together_interviewer_final_payload,
    build_together_suite_v3,
    build_together_suite_v4,
    load_together_suite,
    validate_request_against_role_envelope,
)
from eval.validate_phase4_together import main as validate_main

ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = (
    ROOT / "eval/fixtures/preference_eval_phase4_robustness_v1.json"
)
SUITE_PATH = ROOT / "eval/fixtures/preference_eval_phase4_together_v4.json"
LEGACY_V3_SUITE_PATH = (
    ROOT / "eval/fixtures/preference_eval_phase4_together_v3.json"
)
LEGACY_V2_SUITE_PATH = (
    ROOT / "eval/fixtures/preference_eval_phase4_together_v2.json"
)
LEGACY_SUITE_PATH = (
    ROOT / "eval/fixtures/preference_eval_phase4_together_v1.json"
)
NOW = datetime(2026, 8, 20, 13, 0, tzinfo=timezone.utc)


class DemoOutput(ContractModel):
    choice: str
    confidence: float


OUTPUT_ADAPTER = ProviderResponseContract(adapter=TypeAdapter(DemoOutput))


def profile():
    return load_phase4_robustness_profile(PROFILE_PATH)


def suite() -> Phase4TogetherSuite:
    return load_together_suite(SUITE_PATH)


def prepared_request(
    *,
    role: LLMRole = LLMRole.DIRECT_READOUT,
    input_payload: object | None = None,
    input_token_upper_bound: int = 6_000,
    output_token_upper_bound: int | None = None,
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
        output_token_upper_bound=(
            output_token_upper_bound
            if output_token_upper_bound is not None
            else (1_000 if role is LLMRole.INTERVIEWER else 500)
        ),
        created_at=NOW,
        tool_definitions=tools,
    )


def test_tracked_v4_suite_matches_preserved_builder() -> None:
    loaded = suite()
    expected = build_together_suite_v4(profile())

    assert loaded == expected
    assert content_sha256(loaded) == content_sha256(expected)
    assert len(loaded.candidates) == 3
    assert len(loaded.shared_role_contracts) == 5
    assert content_sha256(loaded) == (
        "aea27b51ed24c8e4c11bfe0648a04ff0e29d25faeb519a9afa95e594a3d84283"
    )


def test_v5_changes_only_the_interviewer_role_contract() -> None:
    legacy = build_together_suite_v4(profile())
    current = build_default_together_suite(profile())
    legacy_contracts = {item.role: item for item in legacy.shared_role_contracts}
    current_contracts = {
        item.role: item for item in current.shared_role_contracts
    }

    assert current.suite_version == 5
    assert current.created_at == datetime(
        2026,
        8,
        26,
        20,
        tzinfo=timezone.utc,
    )
    assert current.catalog == legacy.catalog
    assert current.provider_terms == legacy.provider_terms
    assert current.candidates == legacy.candidates
    assert current.workload == legacy.workload
    for role in LLMRole:
        if role is not LLMRole.INTERVIEWER:
            assert current_contracts[role] == legacy_contracts[role]

    legacy_interviewer = legacy_contracts[LLMRole.INTERVIEWER]
    current_interviewer = current_contracts[LLMRole.INTERVIEWER]
    assert legacy_interviewer.response_schema_version == 2
    assert current_interviewer.response_schema_version == 3
    assert current_interviewer.response_schema_id == (
        "phase4_interviewer_decision_and_tool_contracts_v3"
    )
    assert current_interviewer.prompt_id == "phase4_interviewer_together_v4"
    assert current_interviewer.prompt_version == 4
    assert "selected_question_id" in current_interviewer.prompt_text
    assert "selected_question_sha256" not in current_interviewer.prompt_text
    assert current_interviewer.response_schema_sha256 != (
        legacy_interviewer.response_schema_sha256
    )
    assert current_interviewer.tool_definitions_sha256 == (
        legacy_interviewer.tool_definitions_sha256
    )


def test_v1_suite_is_preserved_as_an_exact_audit_artifact() -> None:
    legacy = load_together_suite(LEGACY_SUITE_PATH)

    assert legacy.suite_version == 1
    assert content_sha256(legacy) == (
        "cb7793244ec640fa336a839d198b8f8e5650cfd20a7a2b9f51a3affc15afa11c"
    )


def test_v2_suite_is_preserved_as_an_exact_audit_artifact() -> None:
    legacy = load_together_suite(LEGACY_V2_SUITE_PATH)

    assert legacy.suite_version == 2
    assert content_sha256(legacy) == (
        "dce672dada8a80cb87f57235ca4b9b44da5c13d44e597b89a63e29d01f67a2a5"
    )


def test_v3_suite_is_preserved_as_an_exact_audit_artifact() -> None:
    legacy = load_together_suite(LEGACY_V3_SUITE_PATH)

    assert legacy == build_together_suite_v3(profile())
    assert content_sha256(legacy) == (
        "657ec77bec315bc55b01bae8bbc3c5fb95b1f584a2a49d9979c515621f9cd9fa"
    )


def test_v4_extractor_contract_exposes_every_runtime_pair_invariant() -> None:
    role_contracts = {item.role: item for item in suite().shared_role_contracts}
    extractor = role_contracts[LLMRole.EVIDENCE_EXTRACTOR]

    assert extractor.prompt_id == "phase4_evidence_extractor_together_v2"
    assert extractor.prompt_version == 2
    assert extractor.prompt_text == EVIDENCE_EXTRACTOR_PROMPT_V2
    assert extractor.prompt_text.startswith(EVIDENCE_EXTRACTOR_PROMPT_V1)
    assert extractor.response_schema_version == 2
    assert "signed value means preference for item_a over item_b" in (
        extractor.prompt_text
    )
    assert "sign reversed" in extractor.prompt_text


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


def test_no_spend_report_labels_envelope_totals_as_non_authorizing() -> None:
    report = build_no_spend_report(suite(), profile())

    assert report.qualification_request_count == 456
    assert report.qualification_projected_cost_microusd == 3_560_400
    assert report.qualification_projected_headroom_microusd == 439_600
    assert report.held_out_request_count == 1_104
    assert report.held_out_projected_cost_microusd_by_candidate == {
        "together_glm_5_2": 16_752_000,
        "together_gpt_oss_120b": 1_936_800,
        "together_nemotron_3_ultra_550b_a55b": 9_072_000,
    }
    assert report.held_out_projected_headroom_microusd_by_candidate == {
        "together_glm_5_2": -3_752_000,
        "together_gpt_oss_120b": 11_063_200,
        "together_nemotron_3_ultra_550b_a55b": 3_928_000,
    }
    assert report.all_candidates_fit_qualification_cap is True
    assert report.all_candidates_fit_held_out_cap is False
    assert report.all_calls_at_envelope_totals_are_non_authorizing is True
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

    assert payload["tool_choice"] == "required"
    assert "response_format" not in payload
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
    assert payload["max_tokens"] == 500

    payload["messages"].extend(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "one"}],
            },
            {"role": "tool", "tool_call_id": "one", "content": "{}"},
        ]
    )
    final = build_together_interviewer_final_payload(
        suite(),
        prepared_request(role=LLMRole.INTERVIEWER),
        payload,
    )
    assert "tools" not in final
    assert "tool_choice" not in final
    assert final["response_format"]["type"] == "json_schema"


def test_interviewer_codec_rejects_an_indivisible_round_budget() -> None:
    with pytest.raises(
        ValueError,
        match="output bound must divide by rounds",
    ):
        build_together_chat_payload(
            suite(),
            prepared_request(
                role=LLMRole.INTERVIEWER,
                output_token_upper_bound=999,
            ),
        )


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


def test_no_spend_report_exposes_an_even_larger_envelope_shortfall() -> None:
    high_cost_suite = suite()
    for usage in (
        high_cost_suite.workload.held_out_selected_candidate.role_usage
    ):
        usage.input_tokens_per_request *= 10

    report = build_no_spend_report(high_cost_suite, profile())

    assert report.all_candidates_fit_held_out_cap is False
    assert (
        report.held_out_projected_headroom_microusd_by_candidate[
            "together_glm_5_2"
        ]
        < -100_000_000
    )


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


def test_validate_cli_accepts_default_v5_builder(tmp_path, capsys) -> None:
    current = build_default_together_suite(profile())
    suite_path = tmp_path / "together_suite_v5.json"
    suite_path.write_text(
        json.dumps(current.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    exit_code = validate_main([str(suite_path), str(PROFILE_PATH)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["suite_sha256"] == content_sha256(current)
    assert payload["network_call_count"] == 0
    assert payload["spend_microusd"] == 0


def test_validate_cli_accepts_the_exact_legacy_v1_audit_artifact(capsys) -> None:
    exit_code = validate_main([str(LEGACY_SUITE_PATH), str(PROFILE_PATH)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["suite_sha256"] == (
        "cb7793244ec640fa336a839d198b8f8e5650cfd20a7a2b9f51a3affc15afa11c"
    )


def test_validate_cli_accepts_the_exact_legacy_v2_audit_artifact(capsys) -> None:
    exit_code = validate_main([str(LEGACY_V2_SUITE_PATH), str(PROFILE_PATH)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["suite_sha256"] == (
        "dce672dada8a80cb87f57235ca4b9b44da5c13d44e597b89a63e29d01f67a2a5"
    )
