from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace

from eval.fixture_io import content_sha256, load_fixture
from eval.phase4_readiness import (
    Phase4TogetherReadinessBundle,
    TogetherExactTokenCounterSet,
    build_qualification_resume_cursor,
    load_exact_tokenizer_from_snapshot,
    load_readiness_bundle,
    qualification_remaining_entries,
    readiness_summary,
    validate_readiness_bundle,
)
from eval.phase4_robustness import load_phase4_robustness_profile
from eval.phase4_semantic import load_authored_semantic_map
from eval.phase4_together import load_together_suite
from eval.prequential import load_session_script
from eval.validate_phase4_readiness import main as validate_main


FIXTURES = Path(__file__).parents[1] / "fixtures"
READINESS_PATH = (
    FIXTURES / "preference_eval_phase4_together_readiness_v3.json"
)
SUITE_PATH = FIXTURES / "preference_eval_phase4_together_v3.json"
PROFILE_PATH = FIXTURES / "preference_eval_phase4_robustness_v1.json"
DEV_FIXTURE_PATH = FIXTURES / "preference_eval_dev_v1.json"
DEV_SESSION_PATH = FIXTURES / "preference_eval_dev_session_v1.json"
DEV_MAP_PATH = FIXTURES / "preference_eval_dev_semantic_map_v1.json"


def public_inputs():
    return (
        load_together_suite(SUITE_PATH),
        load_phase4_robustness_profile(PROFILE_PATH),
        load_fixture(DEV_FIXTURE_PATH),
        load_session_script(DEV_SESSION_PATH),
        load_authored_semantic_map(DEV_MAP_PATH),
    )


def validate(bundle: Phase4TogetherReadinessBundle) -> None:
    suite, profile, fixture, session, semantic_map = public_inputs()
    validate_readiness_bundle(
        bundle,
        suite,
        profile,
        fixture,
        session,
        semantic_map,
    )


def test_tracked_readiness_bundle_validates_and_records_zero_spend():
    bundle = load_readiness_bundle(READINESS_PATH)
    validate(bundle)
    summary = readiness_summary(bundle)

    assert len(bundle.tokenizer_artifacts) == 3
    assert len(bundle.qualification_manifest.entries) == 456
    assert sum(
        row.request_count for row in bundle.held_out_calibration_manifest.rows
    ) == 3312
    retest_rows = [
        row
        for row in bundle.held_out_calibration_manifest.rows
        if row.presentation_kind.value == "retest"
    ]
    assert len(retest_rows) == 6
    assert {row.role.value for row in retest_rows} == {
        "direct_readout",
        "hybrid_readout",
    }
    assert {row.request_count for row in retest_rows} == {96}
    assert bundle.provider_inference_calls_executed == 0
    assert bundle.provider_spend_microusd == 0
    assert bundle.together_api_key_required is False
    assert summary["held_out_projected_cost_microusd_by_candidate"] == {
        "together_glm_5_2": 11_167_563,
        "together_gpt_oss_120b": 1_338_386,
        "together_nemotron_3_ultra_550b_a55b": 7_068_320,
    }
    assert summary[
        "held_out_all_calls_at_envelope_cost_microusd_by_candidate"
    ] == {
        "together_glm_5_2": 16_752_000,
        "together_gpt_oss_120b": 1_936_800,
        "together_nemotron_3_ultra_550b_a55b": 9_072_000,
    }
    assert summary[
        "held_out_sequential_reservation_headroom_microusd_by_candidate"
    ] == {
        "together_glm_5_2": 1_807_037,
        "together_gpt_oss_120b": 11_658_764,
        "together_nemotron_3_ultra_550b_a55b": 5_919_080,
    }


def test_qualification_plan_has_exact_role_and_variant_matrix():
    manifest = load_readiness_bundle(READINESS_PATH).qualification_manifest
    counts = Counter(
        (entry.coordinate.candidate_id, entry.coordinate.role.value)
        for entry in manifest.entries
    )
    for candidate_id in sorted({key[0] for key in counts}):
        assert counts[(candidate_id, "direct_readout")] == 64
        assert counts[(candidate_id, "hybrid_readout")] == 64
        assert counts[(candidate_id, "interviewer")] == 8
        assert counts[(candidate_id, "evidence_extractor")] == 8
        assert counts[(candidate_id, "ontology_proposer")] == 8

    readout_variants = Counter(
        entry.coordinate.variant_id.value
        for entry in manifest.entries
        if entry.coordinate.role.value == "direct_readout"
        and entry.coordinate.candidate_id == "together_glm_5_2"
    )
    assert set(readout_variants.values()) == {8}
    assert len(readout_variants) == 8
    for entry in manifest.entries:
        expected_rounds = (
            2 if entry.coordinate.role.value == "interviewer" else 1
        )
        assert entry.provider_round_count == expected_rounds
        assert len(entry.provider_round_payload_sha256) == expected_rounds
        assert sum(entry.input_token_counts_by_round) == entry.input_token_count


def test_qualification_cursor_resumes_only_from_an_exact_prefix():
    bundle = load_readiness_bundle(READINESS_PATH)
    manifest = bundle.qualification_manifest
    initial = build_qualification_resume_cursor(manifest)
    assert initial.completed_call_count == 0
    assert initial.remaining_call_count == 456
    assert initial.next_call_id == manifest.entries[0].coordinate.call_id

    capability_entries = manifest.entries[:15]
    assert bundle.capability_preflight_call_ids == [
        entry.coordinate.call_id for entry in capability_entries
    ]
    assert len(
        {
            (entry.coordinate.candidate_id, entry.coordinate.role)
            for entry in capability_entries
        }
    ) == 15
    assert all(
        entry.coordinate.variant_id.value == "canonical"
        for entry in capability_entries
    )

    completed = [entry.coordinate.call_id for entry in manifest.entries[:3]]
    resumed = build_qualification_resume_cursor(
        manifest,
        completed_call_ids=completed,
    )
    assert resumed.completed_call_count == 3
    assert resumed.next_call_id == manifest.entries[3].coordinate.call_id

    with pytest.raises(ValueError, match="exact plan prefix"):
        qualification_remaining_entries(
            manifest,
            [manifest.entries[1].coordinate.call_id],
        )


def test_readiness_validator_rejects_projection_tampering():
    payload = json.loads(READINESS_PATH.read_text(encoding="utf-8"))
    projection = payload["token_readiness_receipt"]["candidate_projections"][0]
    projection["qualification_input_token_count"] += 1
    tampered = Phase4TogetherReadinessBundle.model_validate(payload)

    with pytest.raises(ValueError, match="token projection does not reconcile"):
        validate(tampered)


def test_call_plan_rejects_an_input_count_above_its_envelope():
    payload = json.loads(READINESS_PATH.read_text(encoding="utf-8"))
    entry = payload["qualification_manifest"]["entries"][0]
    excess = entry["input_token_upper_bound"] + 1
    delta = excess - entry["input_token_count"]
    entry["input_token_counts_by_round"][0] += delta
    entry["input_token_count"] = excess

    with pytest.raises(ValidationError, match="exceeds its input envelope"):
        Phase4TogetherReadinessBundle.model_validate(payload)


def test_readiness_validator_rejects_held_out_cost_tampering():
    payload = json.loads(READINESS_PATH.read_text(encoding="utf-8"))
    row = payload["held_out_calibration_manifest"]["rows"][0]
    row["projected_cost_microusd"] += 1
    tampered = Phase4TogetherReadinessBundle.model_validate(payload)

    with pytest.raises(
        ValueError,
        match="held-out calibration cost does not reconcile",
    ):
        validate(tampered)


def test_held_out_calibration_rejects_a_flattened_wave():
    payload = json.loads(READINESS_PATH.read_text(encoding="utf-8"))
    rows = payload["held_out_calibration_manifest"]["rows"]
    first = rows[0]
    second = next(
        row
        for row in rows
        if row["candidate_id"] == first["candidate_id"]
        and row["role"] == first["role"]
        and row["wave_index"] == 2
    )
    second["input_token_counts"] = first["input_token_counts"]
    second["input_token_count"] = first["input_token_count"]
    second["maximum_input_tokens_per_request"] = first[
        "maximum_input_tokens_per_request"
    ]

    with pytest.raises(
        ValidationError,
        match="wave input totals must strictly increase",
    ):
        Phase4TogetherReadinessBundle.model_validate(payload)


def test_readiness_summary_is_aggregate_only():
    bundle = load_readiness_bundle(READINESS_PATH)
    summary_text = json.dumps(readiness_summary(bundle), sort_keys=True)
    fixture = load_fixture(DEV_FIXTURE_PATH)

    for measure in fixture.measures:
        assert measure.measure_id not in summary_text
        assert measure.title not in summary_text
        for option in measure.options:
            assert option.option_id not in summary_text
            assert option.label not in summary_text


def test_validator_cli_prints_only_aggregate_output(capsys):
    exit_code = validate_main(
        [
            str(READINESS_PATH),
            str(SUITE_PATH),
            str(PROFILE_PATH),
            str(DEV_FIXTURE_PATH),
            str(DEV_SESSION_PATH),
            str(DEV_MAP_PATH),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert "dev_fiscal_reserve" not in captured.out
    assert '"provider_spend_microusd": 0' in captured.out


def test_tokenizer_artifact_hashes_only_local_tokenizer_files(tmp_path):
    tokenizer = Tokenizer(WordLevel({"[UNK]": 0, "hello": 1}, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = Whitespace()
    tokenizer.save(str(tmp_path / "tokenizer.json"))
    (tmp_path / "tokenizer_config.json").write_text(
        '{"model_max_length": 1024}\n',
        encoding="utf-8",
    )
    suite = load_together_suite(SUITE_PATH)
    candidate = suite.candidates[0].candidate

    loaded = load_exact_tokenizer_from_snapshot(
        candidate,
        tmp_path,
        tokenizer_library_version="test",
    )

    assert loaded.count("hello") == 1
    assert [item.relative_path for item in loaded.artifact.files] == [
        "tokenizer.json",
        "tokenizer_config.json",
    ]
    assert loaded.artifact.candidate_sha256 == content_sha256(candidate)
    payload = {"model": candidate.serving_model_id, "messages": []}
    count = TogetherExactTokenCounterSet(
        {candidate.candidate_id: loaded}
    ).count_payload(candidate.candidate_id, payload)
    assert count.payload_sha256 == content_sha256(payload)
    assert count.input_token_count > 0
