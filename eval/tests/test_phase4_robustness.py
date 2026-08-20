from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from eval.fixture_io import content_sha256
from eval.phase4_protocol import load_phase4_protocol
from eval.phase4_robustness import (
    BudgetSegment,
    ModelCapability,
    OpenWeightModelCandidate,
    PHASE4E_PERTURBATION_EXPECTATIONS,
    Phase4ERobustnessProfile,
    ProviderCallAuthorization,
    ProviderCallUsage,
    ProviderUsageLedger,
    RobustnessExpectation,
    RobustnessPerturbationKind,
    RobustnessPrediction,
    RobustnessVariantBinding,
    aggregate_robustness_comparisons,
    authorize_provider_call,
    build_option_label_variant,
    build_option_order_variant,
    build_robustness_evaluation_binding,
    compare_robustness_predictions,
    load_phase4_robustness_profile,
    load_semantic_review_summary,
    phase4_robustness_profile_summary,
    provider_committed_totals,
    provider_usage_totals,
    validate_phase4_robustness_profile,
    validate_provider_usage_ledger,
    validate_robustness_aggregate_against_policy,
)
from eval.phase4_prediction import expected_top_option_id
from eval.validate_phase4_robustness import main as validate_main

ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = (
    ROOT / "eval/fixtures/preference_eval_phase4_robustness_v1.json"
)
PROTOCOL_PATH = ROOT / "eval/fixtures/preference_eval_phase4_protocol_v1.json"
SEMANTIC_SUMMARY_PATH = (
    ROOT / "eval/review_summaries/semantic_map_summary.json"
)
NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)
ZERO_HASH = "0" * 64
PROFILE_SHA256 = (
    "bd8393916581aac16f365f1d642dc0b0ca3f160ff9896360f69b32060eb02691"
)


def artifacts():
    return (
        load_phase4_robustness_profile(PROFILE_PATH),
        load_phase4_protocol(PROTOCOL_PATH),
        load_semantic_review_summary(SEMANTIC_SUMMARY_PATH),
    )


def usage_ledger(
    profile: Phase4ERobustnessProfile,
    authorizations: list[ProviderCallAuthorization] | None = None,
    calls: list[ProviderCallUsage] | None = None,
) -> ProviderUsageLedger:
    return ProviderUsageLedger(
        ledger_id="provider_usage_test_v1",
        robustness_profile_id=profile.profile_id,
        robustness_profile_version=profile.profile_version,
        robustness_profile_sha256=content_sha256(profile),
        authorizations=authorizations or [],
        calls=calls or [],
    )


def authorization(
    call_id: str,
    *,
    segment: BudgetSegment = BudgetSegment.QUALIFICATION,
    cost: int = 100_000,
    retry_of_call_id: str | None = None,
    created_at: datetime = NOW,
    segment_remaining_before: int | None = None,
    total_remaining_before: int = 20_000_000,
) -> ProviderCallAuthorization:
    return ProviderCallAuthorization(
        call_id=call_id,
        segment=segment,
        model_candidate_id="candidate_one",
        request_sha256=ZERO_HASH,
        retry_of_call_id=retry_of_call_id,
        authorized_max_cost_microusd=cost,
        segment_remaining_before_microusd=(
            (
                3_000_000
                if segment is BudgetSegment.RETRY_RESERVE
                else 13_000_000
                if segment is BudgetSegment.HELD_OUT_STUDY
                else 4_000_000
            )
            if segment_remaining_before is None
            else segment_remaining_before
        ),
        total_remaining_before_microusd=total_remaining_before,
        created_at=created_at,
    )


def usage(
    call_authorization: ProviderCallAuthorization,
    *,
    billed_cost: int | None = None,
    created_at: datetime | None = None,
) -> ProviderCallUsage:
    return ProviderCallUsage(
        call_id=call_authorization.call_id,
        segment=call_authorization.segment,
        model_candidate_id=call_authorization.model_candidate_id,
        request_sha256=call_authorization.request_sha256,
        authorization_sha256=content_sha256(call_authorization),
        billed_cost_microusd=(
            call_authorization.authorized_max_cost_microusd
            if billed_cost is None
            else billed_cost
        ),
        input_tokens=100,
        output_tokens=20,
        cache_hit=False,
        retry_of_call_id=call_authorization.retry_of_call_id,
        created_at=created_at or call_authorization.created_at,
    )


def candidate_payload() -> dict[str, object]:
    return {
        "candidate_id": "candidate_one",
        "artifact_id": "candidate_one_artifact",
        "artifact_version": 1,
        "upstream_model_id": "publisher/model",
        "upstream_model_revision": "exact-revision",
        "weights_manifest_sha256": ZERO_HASH,
        "license_id": "open-weight-license",
        "license_sha256": ZERO_HASH,
        "deployment_mode": "hosted_api",
        "backend_id": "provider_backend",
        "backend_version": 1,
        "serving_model_id": "provider/model",
        "serving_model_revision": "exact-serving-revision",
        "provider_terms_sha256": ZERO_HASH,
        "context_window_tokens": 32_768,
        "capabilities": list(ModelCapability),
    }


def variant_binding(
    kind: RobustnessPerturbationKind,
    *,
    variant_id: str = "variant_one",
) -> RobustnessVariantBinding:
    return RobustnessVariantBinding(
        variant_id=variant_id,
        variant_version=1,
        perturbation_kind=kind,
        variant_sha256=content_sha256(f"variant:{variant_id}"),
        seed=(
            None
            if kind is RobustnessPerturbationKind.PROMPT_PARAPHRASE
            else 42
        ),
        repeat_index=(
            1
            if kind is RobustnessPerturbationKind.STOCHASTIC_REPEAT
            else None
        ),
    )


def prediction(
    prediction_id: str,
    probabilities: dict[str, float],
    *,
    variant_kind: RobustnessPerturbationKind | None = None,
) -> RobustnessPrediction:
    profile, _, _ = artifacts()
    option_order = list(probabilities)
    top = expected_top_option_id(option_order, probabilities)
    return RobustnessPrediction(
        prediction_id=prediction_id,
        evaluation_binding=build_robustness_evaluation_binding(
            profile,
            OpenWeightModelCandidate.model_validate(candidate_payload()),
        ),
        variant_binding=(
            None if variant_kind is None else variant_binding(variant_kind)
        ),
        request_sha256=content_sha256(f"request:{prediction_id}"),
        response_sha256=content_sha256(f"response:{prediction_id}"),
        canonical_option_order=option_order,
        option_probabilities=probabilities,
        top_option_id=top,
        output_valid=True,
    )


def test_committed_profile_validates_and_cli_is_aggregate_only(capsys):
    profile, protocol, semantic_summary = artifacts()

    validate_phase4_robustness_profile(profile, protocol, semantic_summary)
    assert validate_main(
        [
            str(PROFILE_PATH),
            str(PROTOCOL_PATH),
            str(SEMANTIC_SUMMARY_PATH),
        ]
    ) == 0

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload == phase4_robustness_profile_summary(profile)
    assert payload["profile_sha256"] == PROFILE_SHA256
    assert payload["hard_api_budget_usd"] == 20.0
    assert payload["development_candidate_count"] == 3
    assert payload["participant_content_omitted"] is True
    assert "measure_id" not in output
    assert "option_id" not in output


def test_profile_rejects_protocol_and_semantic_summary_drift():
    profile, protocol, semantic_summary = artifacts()
    changed_protocol = protocol.model_copy(
        update={"protocol_version": protocol.protocol_version + 1}
    )
    with pytest.raises(ValueError, match="bind the Phase 4 protocol"):
        validate_phase4_robustness_profile(
            profile,
            changed_protocol,
            semantic_summary,
        )

    changed_summary = semantic_summary.model_copy(
        update={"findings_count": semantic_summary.findings_count + 1}
    )
    with pytest.raises(ValueError, match="bind the semantic approval"):
        validate_phase4_robustness_profile(
            profile,
            protocol,
            changed_summary,
        )


def test_model_policy_requires_every_role_and_candidate_capability():
    profile, _, _ = artifacts()
    policy_payload = profile.model_policy.model_dump(mode="json")
    policy_payload["required_roles"].pop()
    profile_payload = profile.model_dump(mode="json")
    profile_payload["model_policy"] = policy_payload
    with pytest.raises(ValidationError, match="must contain the complete"):
        Phase4ERobustnessProfile.model_validate(profile_payload)

    incomplete_candidate = candidate_payload()
    incomplete_candidate["capabilities"] = [ModelCapability.TOOL_CALLING]
    with pytest.raises(ValidationError, match="must contain the complete"):
        OpenWeightModelCandidate.model_validate(incomplete_candidate)

    with pytest.raises(TypeError):
        PHASE4E_PERTURBATION_EXPECTATIONS[
            RobustnessPerturbationKind.OPTION_ORDER
        ] = RobustnessExpectation.SENSITIVITY_DIAGNOSTIC  # type: ignore[index]


def test_budget_partition_and_pre_call_authorization_are_hard_caps():
    profile, _, _ = artifacts()
    profile_payload = profile.model_dump(mode="json")
    profile_payload["budget_policy"]["segment_caps_microusd"] = {
        "qualification": 5_000_000,
        "held_out_study": 12_000_000,
        "retry_reserve": 3_000_000,
    }
    with pytest.raises(ValidationError, match="must be 4/13/3 USD"):
        Phase4ERobustnessProfile.model_validate(profile_payload)

    first_authorization = authorization(
        "qualification_call",
        cost=3_900_000,
    )
    ledger = usage_ledger(profile, [first_authorization])
    next_authorization = authorize_provider_call(
        ledger,
        profile,
        call_id="next_call",
        segment=BudgetSegment.QUALIFICATION,
        model_candidate_id="candidate_one",
        request_sha256=ZERO_HASH,
        maximum_cost_microusd=100_000,
        created_at=NOW + timedelta(seconds=1),
    )
    assert next_authorization.segment_remaining_before_microusd == 100_000
    assert next_authorization.approved is True
    assert provider_committed_totals(ledger)[
        BudgetSegment.QUALIFICATION
    ] == 3_900_000
    with pytest.raises(ValueError, match="remaining segment budget"):
        authorize_provider_call(
            ledger,
            profile,
            call_id="too_expensive",
            segment=BudgetSegment.QUALIFICATION,
            model_candidate_id="candidate_one",
            request_sha256=ZERO_HASH,
            maximum_cost_microusd=100_001,
            created_at=NOW + timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="call id already exists"):
        authorize_provider_call(
            ledger,
            profile,
            call_id="qualification_call",
            segment=BudgetSegment.QUALIFICATION,
            model_candidate_id="candidate_one",
            request_sha256=ZERO_HASH,
            maximum_cost_microusd=1,
            created_at=NOW + timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="must follow the earlier issuance"):
        authorize_provider_call(
            ledger,
            profile,
            call_id="backdated_call",
            segment=BudgetSegment.QUALIFICATION,
            model_candidate_id="candidate_one",
            request_sha256=ZERO_HASH,
            maximum_cost_microusd=1,
            created_at=NOW - timedelta(seconds=1),
        )

    with pytest.raises(ValidationError, match="must reference an earlier call"):
        authorize_provider_call(
            ledger,
            profile,
            call_id="unlinked_retry",
            segment=BudgetSegment.RETRY_RESERVE,
            model_candidate_id="candidate_one",
            request_sha256=ZERO_HASH,
            maximum_cost_microusd=1,
            created_at=NOW + timedelta(seconds=1),
        )

    tampered_payload = first_authorization.model_dump()
    tampered_payload["segment_remaining_before_microusd"] = 3_999_999
    tampered = ProviderCallAuthorization.model_validate(tampered_payload)
    with pytest.raises(ValueError, match="remaining-budget proof"):
        validate_provider_usage_ledger(
            usage_ledger(profile, [tampered]),
            profile,
        )


def test_usage_ledger_validates_caps_cache_and_retry_lineage():
    profile, _, _ = artifacts()
    first_authorization = authorization("first_call", cost=2_500_000)
    second_authorization = authorization(
        "second_call",
        cost=2_000_000,
        created_at=NOW + timedelta(seconds=1),
        segment_remaining_before=1_500_000,
        total_remaining_before=17_500_000,
    )
    first = usage(first_authorization)
    second = usage(second_authorization)
    over_cap = usage_ledger(
        profile,
        [first_authorization, second_authorization],
        [first, second],
    )
    with pytest.raises(ValueError, match="segment cap"):
        validate_provider_usage_ledger(over_cap, profile)

    retry_authorization = authorization(
        "retry_call",
        segment=BudgetSegment.RETRY_RESERVE,
        cost=250_000,
        retry_of_call_id="first_call",
        created_at=NOW + timedelta(seconds=1),
        total_remaining_before=17_500_000,
    )
    retry = usage(retry_authorization)
    ledger = usage_ledger(
        profile,
        [first_authorization, retry_authorization],
        [first, retry],
    )
    validate_provider_usage_ledger(ledger, profile)
    assert provider_usage_totals(ledger) == {
        BudgetSegment.QUALIFICATION: 2_500_000,
        BudgetSegment.HELD_OUT_STUDY: 0,
        BudgetSegment.RETRY_RESERVE: 250_000,
    }
    assert provider_committed_totals(ledger) == provider_usage_totals(
        ledger
    )

    with pytest.raises(ValidationError, match="reference an earlier call"):
        usage_ledger(
            profile,
            [first_authorization, retry_authorization],
            [retry, first],
        )
    changed_retry_payload = retry.model_dump()
    changed_retry_payload["request_sha256"] = "1" * 64
    changed_retry = ProviderCallUsage.model_validate(changed_retry_payload)
    with pytest.raises(ValidationError, match="does not match its authorization"):
        usage_ledger(
            profile,
            [first_authorization, retry_authorization],
            [first, changed_retry],
        )
    cache_authorization = authorization("cached_call")
    cache_payload = usage(cache_authorization).model_dump()
    cache_payload["cache_hit"] = True
    with pytest.raises(ValidationError, match="cache hits cannot report"):
        ProviderCallUsage.model_validate(cache_payload)
    with pytest.raises(ValidationError, match="must bind an authorization"):
        usage_ledger(profile, [], [first])


def test_completed_call_releases_unused_authorized_budget():
    profile, _, _ = artifacts()
    first_authorization = authorization("estimated_call", cost=1_000_000)
    first_usage = usage(first_authorization, billed_cost=100_000)
    ledger = usage_ledger(
        profile,
        [first_authorization],
        [first_usage],
    )
    validate_provider_usage_ledger(ledger, profile)
    assert provider_committed_totals(ledger)[
        BudgetSegment.QUALIFICATION
    ] == 100_000

    next_authorization = authorize_provider_call(
        ledger,
        profile,
        call_id="after_release",
        segment=BudgetSegment.QUALIFICATION,
        model_candidate_id="candidate_one",
        request_sha256=ZERO_HASH,
        maximum_cost_microusd=3_900_000,
        created_at=NOW + timedelta(seconds=1),
    )
    assert next_authorization.segment_remaining_before_microusd == 3_900_000


def test_phase4e_created_at_fields_require_timezones():
    profile, _, _ = artifacts()
    profile_payload = profile.model_dump(mode="json")
    profile_payload["created_at"] = "2026-08-19T12:00:00"
    with pytest.raises(ValidationError, match="must include a timezone"):
        Phase4ERobustnessProfile.model_validate(profile_payload)

    authorization_payload = authorization("naive_authorization").model_dump()
    authorization_payload["created_at"] = datetime(2026, 8, 19, 12, 0)
    with pytest.raises(ValidationError, match="must include a timezone"):
        ProviderCallAuthorization.model_validate(authorization_payload)

    call_authorization = authorization("naive_usage")
    usage_payload = usage(call_authorization).model_dump()
    usage_payload["created_at"] = datetime(2026, 8, 19, 12, 0)
    with pytest.raises(ValidationError, match="must include a timezone"):
        ProviderCallUsage.model_validate(usage_payload)


def test_option_order_and_label_perturbations_are_deterministic_bijections():
    option_ids = ["one", "two", "three"]
    first_order = build_option_order_variant(option_ids, seed=42)
    second_order = build_option_order_variant(option_ids, seed=42)
    assert first_order == second_order
    assert first_order.variant_option_ids != option_ids
    assert set(first_order.variant_option_ids) == set(option_ids)

    first_labels = build_option_label_variant(option_ids, seed=42)
    second_labels = build_option_label_variant(option_ids, seed=42)
    assert first_labels == second_labels
    assert [item.canonical_option_id for item in first_labels.aliases] == option_ids
    assert len({item.provider_alias for item in first_labels.aliases}) == 3
    many_labels = build_option_label_variant(
        [f"option_{index}" for index in range(27)],
        seed=0,
    )
    assert "option_alias_0_0_aa" in {
        item.provider_alias for item in many_labels.aliases
    }
    colliding_ids = ["option_alias_0_0_a", "other"]
    collision_safe = build_option_label_variant(colliding_ids, seed=0)
    assert {
        item.provider_alias for item in collision_safe.aliases
    }.isdisjoint(colliding_ids)


def test_stochastic_repeat_binds_request_seed_and_bounded_unique_index():
    binding = variant_binding(
        RobustnessPerturbationKind.STOCHASTIC_REPEAT
    )
    assert binding.seed == 42
    assert binding.repeat_index == 1

    payload = binding.model_dump(mode="json")
    payload["repeat_index"] = None
    with pytest.raises(ValidationError, match="request seed and repeat index"):
        RobustnessVariantBinding.model_validate(payload)

    payload = binding.model_dump(mode="json")
    payload["repeat_index"] = 4
    with pytest.raises(ValidationError, match="less than or equal to 3"):
        RobustnessVariantBinding.model_validate(payload)

    canonical = prediction("canonical_repeat", {"one": 0.5, "two": 0.5})
    repeated = prediction(
        "repeated",
        {"one": 0.5, "two": 0.5},
        variant_kind=RobustnessPerturbationKind.STOCHASTIC_REPEAT,
    )
    comparison = compare_robustness_predictions(
        canonical,
        repeated,
        comparison_id="repeat_one",
    )
    duplicate = comparison.model_copy(
        update={"comparison_id": "repeat_duplicate"}
    )
    with pytest.raises(ValueError, match="distinct indices"):
        aggregate_robustness_comparisons([comparison, duplicate])


def test_robustness_comparison_and_aggregate_reconcile():
    canonical = prediction("canonical", {"one": 0.7, "two": 0.3})
    variant = prediction(
        "variant",
        {"one": 0.4, "two": 0.6},
        variant_kind=RobustnessPerturbationKind.PROMPT_PARAPHRASE,
    )
    comparison = compare_robustness_predictions(
        canonical,
        variant,
        comparison_id="comparison_one",
    )
    assert comparison.top_choice_flipped is True
    assert comparison.max_absolute_probability_delta == pytest.approx(0.3)
    assert comparison.jensen_shannon_divergence is not None
    assert comparison.jensen_shannon_divergence > 0.0

    invalid = RobustnessPrediction(
        prediction_id="invalid_variant",
        evaluation_binding=canonical.evaluation_binding,
        variant_binding=variant_binding(
            RobustnessPerturbationKind.PROMPT_PARAPHRASE,
            variant_id="invalid_variant",
        ),
        request_sha256=ZERO_HASH,
        canonical_option_order=["one", "two"],
        output_valid=False,
        failure_code="schema_failure",
    )
    invalid_comparison = compare_robustness_predictions(
        canonical,
        invalid,
        comparison_id="comparison_two",
    )
    aggregate = aggregate_robustness_comparisons(
        [comparison, invalid_comparison]
    )
    assert aggregate.comparison_count == 2
    assert aggregate.valid_comparison_count == 1
    assert aggregate.invalid_output_rate == 0.5
    assert aggregate.top_choice_flip_rate == 1.0


def test_shared_top_option_tie_rule_and_jsd_bits_are_explicit():
    near_tie = prediction(
        "near_tie",
        {"a": 0.5 - 1e-13, "b": 0.5 + 1e-13},
    )
    assert near_tie.top_option_id == "a"
    wrong_top_payload = near_tie.model_dump(mode="json")
    wrong_top_payload["top_option_id"] = "b"
    with pytest.raises(ValidationError, match="canonical display order"):
        RobustnessPrediction.model_validate(wrong_top_payload)

    canonical = prediction("certain_a", {"a": 1.0, "b": 0.0})
    variant = prediction(
        "certain_b",
        {"a": 0.0, "b": 1.0},
        variant_kind=RobustnessPerturbationKind.PROMPT_PARAPHRASE,
    )
    comparison = compare_robustness_predictions(
        canonical,
        variant,
        comparison_id="max_jsd",
    )
    assert comparison.jensen_shannon_divergence == pytest.approx(1.0)
    invalid_jsd_payload = comparison.model_dump(mode="json")
    invalid_jsd_payload["jensen_shannon_divergence"] = 1.000_001
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        comparison.__class__.model_validate(invalid_jsd_payload)


def test_robustness_aggregate_rejects_mixed_perturbation_classes():
    canonical = prediction("canonical", {"one": 0.5, "two": 0.5})
    variant = prediction(
        "variant",
        {"one": 0.5, "two": 0.5},
        variant_kind=RobustnessPerturbationKind.PROMPT_PARAPHRASE,
    )
    prompt = compare_robustness_predictions(
        canonical,
        variant,
        comparison_id="prompt_comparison",
    )
    order = prompt.model_copy(
        update={
            "comparison_id": "order_comparison",
            "variant_binding": variant_binding(
                RobustnessPerturbationKind.OPTION_ORDER,
                variant_id="order_variant",
            ),
            "perturbation_kind": RobustnessPerturbationKind.OPTION_ORDER,
            "expectation": RobustnessExpectation.STRICT_EQUIVARIANCE,
        }
    )
    with pytest.raises(ValueError, match="one perturbation class"):
        aggregate_robustness_comparisons([prompt, order])

    other_binding = prompt.evaluation_binding.model_copy(
        update={"model_candidate_id": "candidate_two"}
    )
    other_candidate = prompt.model_copy(
        update={
            "comparison_id": "other_candidate_comparison",
            "evaluation_binding": other_binding,
        }
    )
    with pytest.raises(ValueError, match="one exact evaluation binding"):
        aggregate_robustness_comparisons([prompt, other_candidate])


def test_strict_transform_flip_fails_the_frozen_policy():
    profile, _, _ = artifacts()
    canonical = prediction("canonical", {"one": 0.7, "two": 0.3})
    flipped = prediction(
        "flipped",
        {"one": 0.3, "two": 0.7},
        variant_kind=RobustnessPerturbationKind.OPTION_ORDER,
    )
    comparison = compare_robustness_predictions(
        canonical,
        flipped,
        comparison_id="strict_comparison",
    )
    aggregate = aggregate_robustness_comparisons([comparison])
    with pytest.raises(ValueError, match="changed the top choice"):
        validate_robustness_aggregate_against_policy(
            aggregate,
            profile,
            OpenWeightModelCandidate.model_validate(candidate_payload()),
        )

    other_candidate_payload = candidate_payload()
    other_candidate_payload["candidate_id"] = "candidate_two"
    with pytest.raises(ValueError, match="exact profile and candidate"):
        validate_robustness_aggregate_against_policy(
            aggregate,
            profile,
            OpenWeightModelCandidate.model_validate(other_candidate_payload),
        )

    comparison_payload = comparison.model_dump(mode="json")
    comparison_payload["expectation"] = "sensitivity_diagnostic"
    with pytest.raises(ValidationError, match="does not match perturbation"):
        comparison.__class__.model_validate(comparison_payload)


def test_cli_failure_omits_invalid_input(capsys, tmp_path):
    planted = "PLANTED_PHASE4_PRIVATE_CONTENT"
    invalid_profile = tmp_path / "invalid.json"
    invalid_profile.write_text(
        json.dumps({"private_text": planted}),
        encoding="utf-8",
    )

    assert validate_main(
        [
            str(invalid_profile),
            str(PROTOCOL_PATH),
            str(SEMANTIC_SUMMARY_PATH),
        ]
    ) == 1
    captured = capsys.readouterr()
    assert planted not in captured.out
    assert planted not in captured.err
    assert "restricted details omitted" in captured.err
