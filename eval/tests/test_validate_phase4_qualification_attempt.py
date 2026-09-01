from __future__ import annotations

import json
from pathlib import Path

from eval import validate_phase4_qualification_attempt as validator_cli


FIXTURES = Path(__file__).parents[1] / "fixtures"
PLANTED_TEXT = "tgp_v1_PRIVATE_VALIDATOR_TEXT_MUST_NOT_APPEAR"


def _argv(*, source_proof: Path | None = None) -> list[str]:
    return [
        str(FIXTURES / "preference_eval_phase4_together_v5.json"),
        str(FIXTURES / "preference_eval_phase4_together_readiness_v5.json"),
        str(FIXTURES / "preference_eval_phase4_together_v6.json"),
        str(FIXTURES / "preference_eval_phase4_together_readiness_v6.json"),
        str(
            source_proof
            or FIXTURES
            / "preference_eval_phase4_qualification_attempt_source_proof_v2.json"
        ),
        str(
            FIXTURES
            / "preference_eval_phase4_two_deployment_qualification_attempt_v2.json"
        ),
        str(FIXTURES / "preference_eval_phase4_robustness_v1.json"),
        str(FIXTURES / "preference_eval_dev_v1.json"),
        str(FIXTURES / "preference_eval_dev_session_v1.json"),
        str(FIXTURES / "preference_eval_dev_semantic_map_v1.json"),
    ]


def test_public_validator_accepts_tracked_attempt_and_reports_aggregates(
    capsys,
) -> None:
    assert validator_cli.main(_argv()) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    summary = json.loads(captured.out)
    assert summary["candidate_count"] == 2
    assert summary["scoped_coordinate_count"] == 304
    assert summary["carried_success_count"] == 0
    assert summary["provider_call_count"] == 304
    assert summary["conformance_stage_call_count"] == 4
    assert summary["private_source_proof_rebuild_performed"] is False
    assert summary["provider_inference_calls_executed"] == 0
    assert summary["provider_spend_microusd"] == 0
    assert "private_runs" not in captured.out


def test_public_validator_rejects_private_path_before_reading(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    private_proof = tmp_path / "eval" / "private_runs" / "proof.json"
    reads: list[Path] = []

    def forbidden_read(path: Path, *args, **kwargs):
        reads.append(path)
        raise AssertionError("public validator must reject before reads")

    monkeypatch.setattr(Path, "read_text", forbidden_read)
    assert validator_cli.main(_argv(source_proof=private_proof)) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "restricted details omitted" in captured.err
    assert reads == []


def test_public_validator_omits_planted_invalid_input(
    tmp_path,
    capsys,
) -> None:
    invalid_proof = tmp_path / "source_proof.json"
    invalid_proof.write_text(
        json.dumps({"private_payload": PLANTED_TEXT}),
        encoding="utf-8",
    )

    assert validator_cli.main(_argv(source_proof=invalid_proof)) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "restricted details omitted" in captured.err
    assert PLANTED_TEXT not in captured.err
    assert "private_payload" not in captured.err
