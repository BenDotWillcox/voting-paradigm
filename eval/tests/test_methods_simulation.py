"""Tests for the voting-methods simulation and its committed benchmark."""

import csv
import gzip
import io
import json
from pathlib import Path

import pytest

from eval.methods_simulation import (
    METHODS,
    ElectionRecord,
    SimulationConfig,
    record_from_row,
    record_row,
    records_from_rows,
    run_election,
    run_simulation,
    summarize,
    wilson_interval,
)

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "eval" / "benchmarks" / "methods_simulation_v1"
PAGE = ROOT / "public" / "data" / "methods" / "simulation.json"
SAMPLES = ROOT / "public" / "data" / "methods" / "samples.json"
SMALL = SimulationConfig(elections=30, candidate_counts=(3, 5))


def committed_records() -> list[ElectionRecord]:
    text = gzip.decompress((BENCHMARK / "elections.csv.gz").read_bytes()).decode("utf-8")
    rows = list(csv.reader(io.StringIO(text)))
    return records_from_rows(rows[1:])


class TestWilsonInterval:
    def test_no_successes(self):
        low, high = wilson_interval(0, 10)

        assert low == 0.0
        assert high == pytest.approx(0.2775, abs=1e-4)

    def test_half(self):
        low, high = wilson_interval(50, 100)

        assert (low, high) == pytest.approx((0.4038, 0.5962), abs=1e-4)

    def test_empty_sample_is_uninformative(self):
        assert wilson_interval(0, 0) == (0.0, 1.0)


class TestStudy:
    def test_an_election_depends_only_on_its_coordinates(self):
        assert run_election(SMALL, 4, 17) == run_election(SimulationConfig(), 4, 17)

    def test_worker_count_does_not_change_the_records(self):
        assert run_simulation(SMALL, workers=1) == run_simulation(SMALL, workers=2)

    def test_records_round_trip_through_csv(self):
        record = run_election(SMALL, 5, 3)

        assert record_from_row(record_row(record)) == record

    def test_summary_counts(self):
        records = run_simulation(SMALL)
        summary = summarize(records, SMALL)
        five = summary["by_candidates"][1]

        assert five["elections"] == 30
        assert five["condorcet_efficiency"]["ranked_pairs"]["rate"] == 1.0
        assert len(five["disagreement"]) == len(METHODS) * (len(METHODS) - 1) // 2


class TestCommittedBenchmark:
    def test_summary_matches_the_elections(self):
        config = SimulationConfig(**{
            **json.loads((BENCHMARK / "config.json").read_text(encoding="utf-8")),
        })
        stored = json.loads((BENCHMARK / "summary.json").read_text(encoding="utf-8"))

        assert summarize(committed_records(), config) == stored

    def test_page_summary_is_the_benchmark_summary(self):
        stored = json.loads((BENCHMARK / "summary.json").read_text(encoding="utf-8"))
        page = json.loads(PAGE.read_text(encoding="utf-8"))

        assert {k: v for k, v in page.items() if k not in ("benchmark", "source_sha256")} == stored

    def test_irv_ties_are_classified_exactly_when_irv_was_not_decisive(self):
        irv = METHODS.index("irv")

        for record in committed_records():
            assert (record.irv_tie != "") == (not record.decisive[irv])

    @pytest.mark.parametrize("candidates", [3, 4, 5])
    def test_a_sample_of_elections_regenerates(self, candidates):
        records = {(r.candidates, r.index): r for r in committed_records()}
        config = SimulationConfig()

        for index in range(0, config.elections, 997):
            assert run_election(config, candidates, index) == records[(candidates, index)]


class TestPageSamples:
    """The page's sample elections (scripts/build_methods_artifacts.py) are the study's."""

    def samples(self) -> list[dict]:
        return json.loads(SAMPLES.read_text(encoding="utf-8"))["samples"]

    def test_each_sample_is_the_committed_election(self):
        records = {(r.candidates, r.index): r for r in committed_records()}
        for sample in self.samples():
            record = records[(sample["candidates"], sample["index"])]

            assert sample["winners"] == dict(zip(METHODS, record.winners)), sample["id"]
            assert sample["condorcet"] == record.condorcet
            assert len(sample["voter_positions"]) == SimulationConfig().voters

    def test_each_sample_is_the_first_to_match_its_rule(self):
        distinct = {"agree": 1, "split": 3}
        records = [r for r in committed_records() if r.candidates == 3]
        for sample in self.samples():
            matches = [
                r for r in records if all(r.decisive) and len(set(r.winners)) == distinct[sample["id"]]
            ]

            assert sample["index"] == matches[0].index, sample["id"]
            assert (sample["matching"], sample["of"]) == (len(matches), len(records)), sample["id"]
