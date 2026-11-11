"""Tests for the curated scenario file and the population it runs on."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from delegation import (
    create_category,
    eligible_voters,
    resolve_ballot_paper,
)
from delegation.scenario import (
    SCENARIO_PATH,
    SCENARIO_SIMULATION,
    InvalidScenarioError,
    load_scenario,
)
from delegation.simulate import CITY, VIEWER, district_id, simulate_network

ROOT = Path(__file__).resolve().parents[2]
SCENARIO = load_scenario()
SIMULATION = simulate_network(
    SCENARIO.categories, SCENARIO_SIMULATION, SCENARIO.nesting
)


class TestScenarioFile:
    def test_pool_papers_and_judgments(self) -> None:
        assert len(SCENARIO.categories) == 30
        assert [(entry.id, entry.paper.jurisdiction) for entry in SCENARIO.papers] == [
            ("city-general", CITY),
            ("district-2-special", district_id(2)),
        ]
        assert [len(entry.paper.questions) for entry in SCENARIO.papers] == [15, 5]
        assert len(SCENARIO.judgments) == 20 * 30
        assert SCENARIO.model == "jev-1.14.0"

    def test_nesting_is_between_pool_categories_and_includes_tree_frogs(self) -> None:
        frogs = create_category("the well-being of tree frogs in the Amazon").id
        environment = create_category("the environment and conservation").id
        assert (frogs, environment) in SCENARIO.nesting
        assert len(SCENARIO.nesting) == 11

    def test_lookups(self) -> None:
        assert SCENARIO.paper("city-general").title == "City general ballot"
        assert SCENARIO.category(SCENARIO.categories[0].id) == SCENARIO.categories[0]
        assert SCENARIO.category("cat_missing") is None
        with pytest.raises(KeyError):
            SCENARIO.paper("no such paper")

    def test_the_file_carries_no_evaluation_labels(self) -> None:
        text = SCENARIO_PATH.read_text(encoding="utf-8")
        assert "acceptable" not in text and "squarely_inside" not in text

    def test_the_file_matches_a_rebuild_from_the_recorded_answers(self) -> None:
        rebuilt = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; sys.path.insert(0, 'scripts');"
                "import build_delegation_scenario as b; sys.stdout.buffer.write(b.scenario_bytes())",
            ],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        assert json.loads(rebuilt) == json.loads(
            SCENARIO_PATH.read_text(encoding="utf-8")
        )

    def broken(self, tmp_path: Path, **changes: object) -> Path:
        raw = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
        raw.update(changes)
        path = tmp_path / "scenario.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        return path

    def test_wrong_schema_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidScenarioError):
            load_scenario(self.broken(tmp_path, schema="other"))

    def test_missing_judgment_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidScenarioError):
            load_scenario(self.broken(tmp_path, judgments={}))

    def test_category_id_must_match_its_text(self, tmp_path: Path) -> None:
        categories = [{"id": "cat_wrong", "text": "all things taxes"}]
        with pytest.raises(InvalidScenarioError):
            load_scenario(self.broken(tmp_path, categories=categories))

    def test_nesting_outside_the_pool_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidScenarioError):
            load_scenario(self.broken(tmp_path, nesting=[["cat_a", "cat_b"]]))


class TestScenarioPopulation:
    def test_every_question_resolves_for_every_eligible_voter(self) -> None:
        for entry in SCENARIO.papers:
            voters = eligible_voters(SIMULATION.network, entry.paper.jurisdiction)
            resolutions = resolve_ballot_paper(
                SIMULATION.network, entry.paper, SCENARIO.judgments
            )
            for resolution in resolutions.values():
                assert resolution.voters == voters
                assert sum(resolution.weights().values()) == len(voters)

    def test_only_district_two_is_issued_the_special_ballot(self) -> None:
        special = SCENARIO.paper("district-2-special").paper
        voters = eligible_voters(SIMULATION.network, special.jurisdiction)
        assert len(voters) == SCENARIO_SIMULATION.residents_per_district
        assert VIEWER not in voters
        assert all(voter.startswith("d2-") for voter in voters)

    def test_the_viewer_answers_for_voters_in_a_district_they_do_not_live_in(
        self,
    ) -> None:
        special = SCENARIO.paper("district-2-special").paper
        resolutions = resolve_ballot_paper(
            SIMULATION.network, special, SCENARIO.judgments
        )
        held = {
            question: resolution.weights().get(VIEWER, 0)
            for question, resolution in resolutions.items()
        }
        assert max(held.values()) >= 1

    def test_delegation_matters_on_the_general_ballot(self) -> None:
        general = SCENARIO.paper("city-general").paper
        resolutions = resolve_ballot_paper(
            SIMULATION.network, general, SCENARIO.judgments
        )
        delegated = [
            sum(trace.delegated for trace in resolution.traces.values())
            for resolution in resolutions.values()
        ]
        # The city flag belongs to no category, so nobody delegates it.
        assert delegated[-1] == 0
        assert sum(count > 20 for count in delegated) >= 10

    def test_a_narrower_category_overrules_a_broader_one_somewhere(self) -> None:
        general = SCENARIO.paper("city-general").paper
        resolutions = resolve_ballot_paper(
            SIMULATION.network, general, SCENARIO.judgments
        )
        assert any(
            decision.set_aside
            for resolution in resolutions.values()
            for decision in resolution.decisions.values()
        )
