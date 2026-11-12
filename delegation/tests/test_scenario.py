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
        assert len(SCENARIO.papers) == 12
        assert [
            (entry.id, entry.paper.jurisdiction) for entry in SCENARIO.open_papers
        ] == [
            ("district-2-special-2", district_id(2)),
            ("city-general-3", CITY),
            ("district-1-special-3", district_id(1)),
            ("city-advisory-2", CITY),
        ]
        assert len(SCENARIO.closed_papers) == 8
        assert all(entry.closes_in_days < 0 for entry in SCENARIO.closed_papers)
        # Every labelled question is used once.
        assert len(SCENARIO.questions) == 68
        assert len(SCENARIO.judgments) == 68 * 30
        assert SCENARIO.model == "jev-1.14.0"

    def test_nesting_is_between_pool_categories_and_includes_tree_frogs(self) -> None:
        frogs = create_category("the well-being of tree frogs in the Amazon").id
        environment = create_category("the environment and conservation").id
        assert (frogs, environment) in SCENARIO.nesting
        assert len(SCENARIO.nesting) == 11

    def test_lookups(self) -> None:
        assert SCENARIO.paper("city-general-3").title == "Port Alder general ballot"
        assert SCENARIO.measure("q03").label == "Measure B"
        with pytest.raises(KeyError):
            SCENARIO.measure("q99")
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

    def viewer(self, **changes: object) -> dict[str, object]:
        raw = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))["viewer"]
        raw.update(changes)
        return dict(raw)

    def test_the_viewer_starts_with_eight_pool_delegations(self) -> None:
        viewer = SCENARIO.viewer
        pool = {category.text for category in SCENARIO.categories}
        assert len(viewer.delegations) == 8
        assert {text for text, _ in viewer.delegations} <= pool
        assert all(
            delegate in SIMULATION.network.persons for _, delegate in viewer.delegations
        )
        closed = {
            question.id
            for entry in SCENARIO.closed_papers
            for question in entry.paper.questions
        }
        assert viewer.missed and viewer.voted_directly
        assert viewer.missed | viewer.voted_directly <= closed

    def test_a_viewer_category_outside_the_pool_is_rejected(
        self, tmp_path: Path
    ) -> None:
        delegations = [{"category": "something nobody judged", "delegate": "d1-003"}]
        with pytest.raises(InvalidScenarioError):
            load_scenario(
                self.broken(tmp_path, viewer=self.viewer(delegations=delegations))
            )

    def test_a_missed_question_must_have_closed(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidScenarioError):
            load_scenario(self.broken(tmp_path, viewer=self.viewer(missed=["q01"])))

    def test_a_paper_cannot_close_today(self, tmp_path: Path) -> None:
        raw = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
        raw["ballot_papers"][0]["closes_in_days"] = 0
        with pytest.raises(InvalidScenarioError):
            load_scenario(self.broken(tmp_path, ballot_papers=raw["ballot_papers"]))

    def test_a_paper_must_open_before_it_closes(self, tmp_path: Path) -> None:
        raw = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
        raw["ballot_papers"][0]["opens_in_days"] = raw["ballot_papers"][0]["closes_in_days"]
        with pytest.raises(InvalidScenarioError):
            load_scenario(self.broken(tmp_path, ballot_papers=raw["ballot_papers"]))

    def test_an_open_paper_has_already_opened(self) -> None:
        for entry in SCENARIO.open_papers:
            assert entry.opens_in_days <= 0 < entry.closes_in_days


class TestMeasures:
    def test_every_measure_has_what_a_ballot_paper_prints(self) -> None:
        for entry in SCENARIO.papers:
            labels = [measure.label for measure in entry.measures]
            assert labels == sorted(labels) and len(set(labels)) == len(labels)
            for measure in entry.measures:
                assert measure.wording.endswith((".", "?"))
                assert measure.kind and measure.fiscal and measure.placed_by
                if measure.ballot_type == "single_choice":
                    assert [o.id for o in measure.question.options] == ["yes", "no"]
                    assert measure.argument_for and measure.argument_against
                else:
                    assert len(measure.question.options) >= 3
                    assert set(measure.option_notes) == {
                        o.id for o in measure.question.options
                    }

    def test_some_measures_are_ranked_and_some_take_approvals(self) -> None:
        types = {
            measure.question.id: measure.ballot_type
            for entry in SCENARIO.papers
            for measure in entry.measures
            if measure.ballot_type != "single_choice"
        }
        assert types == {
            "q41": "ranked",
            "q66": "ranked",
            "q60": "approval",
            "q67": "approval",
        }
        # One of each has closed and one of each is open.
        closed = {q.id for entry in SCENARIO.closed_papers for q in entry.paper.questions}
        assert {"q41", "q67"} <= closed and not {"q66", "q60"} & closed

    def test_a_sited_measure_knows_its_place(self) -> None:
        assert SCENARIO.measure("q34").site == (0.3, 0.3)
        assert SCENARIO.measure("q03").site is None
        # A choice among sites has no single place.
        assert SCENARIO.measure("q60").site is None

    def test_provisional_questions_are_the_reworded_ones(self) -> None:
        assert SCENARIO.provisional <= {q.id for q in SCENARIO.questions}

    def test_an_unknown_ballot_type_is_rejected(self, tmp_path: Path) -> None:
        raw = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
        raw["ballot_papers"][0]["measures"][0]["ballot_type"] = "score"
        path = tmp_path / "scenario.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(InvalidScenarioError):
            load_scenario(path)


class TestViewerPast:
    def test_changes_lead_to_the_starting_delegations(self) -> None:
        viewer = SCENARIO.viewer
        assert viewer.delegations_on(0) == viewer.delegations
        assert viewer.delegations_on(-400) == ()
        # The account opened with four categories, two of them since moved.
        opened = dict(viewer.delegations_on(-340))
        assert set(opened) == {
            "public schools and education",
            "all things taxes",
            "the environment and conservation",
            "housing and land use",
        }
        today = dict(viewer.delegations)
        assert opened["housing and land use"] != today["housing and land use"]
        assert dict(viewer.delegations_on(-300))["housing and land use"] == today[
            "housing and land use"
        ]

    def test_every_past_delegate_is_a_person(self) -> None:
        for change in SCENARIO.viewer_changes(VIEWER):
            assert change.delegator == VIEWER and change.day < 0
            for person in (change.before, change.after):
                assert person is None or person in SIMULATION.network.persons

    def test_a_change_that_does_not_lead_to_today_is_rejected(
        self, tmp_path: Path
    ) -> None:
        raw = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
        raw["viewer"]["changes"].append(
            {"day": -5, "category": "all things taxes", "before": None, "after": "d1-001"}
        )
        path = tmp_path / "scenario.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(InvalidScenarioError):
            load_scenario(path)


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
        special = SCENARIO.paper("district-2-special-2").paper
        voters = eligible_voters(SIMULATION.network, special.jurisdiction)
        assert len(voters) == SCENARIO_SIMULATION.residents_per_district
        assert VIEWER not in voters
        assert all(voter.startswith("d2-") for voter in voters)

    def test_the_viewer_answers_for_voters_in_a_district_they_do_not_live_in(
        self,
    ) -> None:
        special = SCENARIO.paper("district-2-special-2").paper
        resolutions = resolve_ballot_paper(
            SIMULATION.network, special, SCENARIO.judgments
        )
        held = {
            question: resolution.weights().get(VIEWER, 0)
            for question, resolution in resolutions.items()
        }
        assert max(held.values()) >= 1

    def test_delegation_matters_on_the_general_ballot(self) -> None:
        general = SCENARIO.paper("city-general-3").paper
        resolutions = resolve_ballot_paper(
            SIMULATION.network, general, SCENARIO.judgments
        )
        delegated = [
            sum(trace.delegated for trace in resolution.traces.values())
            for resolution in resolutions.values()
        ]
        assert sum(count > 20 for count in delegated) >= 10

    def test_nobody_delegates_a_question_about_no_category(self) -> None:
        advisory = SCENARIO.paper("city-advisory-2").paper
        resolutions = resolve_ballot_paper(
            SIMULATION.network, advisory, SCENARIO.judgments
        )
        flag = resolutions["q66"]  # New city flag
        assert sum(trace.delegated for trace in flag.traces.values()) == 0

    def test_a_narrower_category_overrules_a_broader_one_somewhere(self) -> None:
        general = SCENARIO.paper("city-general-3").paper
        resolutions = resolve_ballot_paper(
            SIMULATION.network, general, SCENARIO.judgments
        )
        assert any(
            decision.set_aside
            for resolution in resolutions.values()
            for decision in resolution.decisions.values()
        )
