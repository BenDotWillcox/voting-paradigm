from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import pytest

from eval.assemble_phase4_qualification_attempt import (
    _require_new_distinct_outputs,
    _write_once,
    main,
    tracked_qualification_attempt_receipt_output,
)
from eval.phase4_qualification_io import REPOSITORY_ROOT


@pytest.mark.parametrize(
    "relative",
    [
        "eval/results/receipt.json",
        "eval/restricted_bank/receipt.json",
        "eval/private_runs/receipt.json",
    ],
)
def test_attempt_v2_receipt_path_is_exactly_review_summaries(relative) -> None:
    with pytest.raises(ValueError, match="review_summaries"):
        tracked_qualification_attempt_receipt_output(
            REPOSITORY_ROOT / relative
        )

    accepted = tracked_qualification_attempt_receipt_output(
        REPOSITORY_ROOT / "eval/review_summaries/receipt.json"
    )
    assert accepted.parent.name == "review_summaries"


def test_existing_receipt_blocks_before_private_result_write(tmp_path) -> None:
    private_result = tmp_path / "private_result.json"
    aggregate_receipt = tmp_path / "aggregate_receipt.json"
    aggregate_receipt.write_text("already exists", encoding="utf-8")

    with pytest.raises(ValueError, match="result output already exists"):
        _require_new_distinct_outputs(
            private_result,
            aggregate_receipt,
            [],
        )

    assert not private_result.exists()


def test_attempt_v2_outputs_are_written_once(tmp_path) -> None:
    output = tmp_path / "receipt.json"

    _write_once(output, '{"safe":true}')

    assert output.read_text(encoding="utf-8") == '{"safe":true}\n'
    with pytest.raises(ValueError, match="result output already exists"):
        _write_once(output, '{"safe":false}')
    assert output.read_text(encoding="utf-8") == '{"safe":true}\n'


def test_cli_path_error_does_not_echo_restricted_path(capsys, tmp_path) -> None:
    planted = "PLANTED_RESTRICTED_ATTEMPT_RESULT_TEXT"
    args = Namespace(private_output_directory=tmp_path / planted)
    with patch(
        "eval.assemble_phase4_qualification_attempt.build_parser"
    ) as parser:
        parser.return_value.parse_args.return_value = args
        assert main([]) == 1

    captured = capsys.readouterr()
    assert planted not in captured.err
    assert "restricted details omitted" in captured.err
