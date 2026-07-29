"""Tests for loading and hashing human-evaluation fixtures."""

import json
from pathlib import Path

from eval.contracts import MeasureDomain
from eval.fixture_io import (
    build_fixture_manifest,
    content_sha256,
    load_fixture,
    validate_development_fixture,
)
from eval.validate_fixture import main

FIXTURE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "preference_eval_dev_v1.json"
)


def test_development_fixture_covers_each_domain_once():
    fixture = load_fixture(FIXTURE_PATH)

    validate_development_fixture(fixture)
    assert len(fixture.measures) == 8
    assert {measure.domain for measure in fixture.measures} == set(MeasureDomain)


def test_manifest_is_deterministic_and_measure_sorted():
    fixture = load_fixture(FIXTURE_PATH)

    first = build_fixture_manifest(fixture)
    second = build_fixture_manifest(fixture)
    assert first == second
    assert len(first.fixture_sha256) == 64
    assert [entry.measure_id for entry in first.measures] == sorted(
        entry.measure_id for entry in first.measures
    )


def test_fixture_round_trips_without_database():
    fixture = load_fixture(FIXTURE_PATH)

    replayed = fixture.__class__.model_validate_json(fixture.model_dump_json())
    assert replayed == fixture


def test_canonical_hash_ignores_source_json_formatting(tmp_path):
    fixture = load_fixture(FIXTURE_PATH)
    parsed = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    reformatted_path = tmp_path / "reformatted.json"
    reformatted_path.write_text(
        json.dumps(parsed, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )

    assert content_sha256(fixture) == content_sha256(
        load_fixture(reformatted_path)
    )


def test_cli_prints_machine_readable_manifest(capsys):
    exit_code = main([str(FIXTURE_PATH)])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["schema_version"] == "preference_eval_manifest.v1"
    assert output["fixture_id"] == "preference_eval_dev_v1"
    assert len(output["measures"]) == 8
