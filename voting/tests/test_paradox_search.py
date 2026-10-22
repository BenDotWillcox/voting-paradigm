"""Tests for the paradox search and its committed artifacts."""

import dataclasses
import json
from pathlib import Path

import numpy as np
import pytest

from voting import combine, create_ranked_profile
from voting.search import (
    RANKED_METHODS,
    AddVoters,
    SpecimenError,
    certify,
    outcome,
    profile_count,
    profiles,
    rankings,
    search,
    specimen_from_json,
    specimen_to_json,
)
from voting.search.tables import build_winner_table

ARTIFACTS = Path(__file__).resolve().parents[2] / "public" / "data" / "methods"
ABC = ("A", "B", "C")


def load(name: str) -> dict[str, object]:
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def committed_searches() -> list[dict]:
    return load("specimens.json")["searches"]  # type: ignore[return-value]


def committed_specimens() -> list[dict]:
    return [record["specimen"] for record in committed_searches() if record["specimen"]]


class TestEnumeration:
    @pytest.mark.parametrize("voters", range(0, 6))
    def test_count_matches_formula(self, voters):
        assert len(list(profiles(ABC, voters))) == profile_count(3, voters)

    def test_profiles_are_distinct_and_canonical(self):
        generated = list(profiles(ABC, 4))

        assert len(set(generated)) == len(generated)
        for profile in generated:
            rebuilt = create_ranked_profile(ABC, [(c, list(r)) for c, r in profile.rows])
            assert rebuilt == profile

    def test_order_starts_with_everyone_on_the_first_ranking(self):
        first = next(profiles(ABC, 3))

        assert first.rows == ((3, ("A", "B", "C")),)


class TestDecisiveOutcomes:
    def test_irv_batch_elimination_is_not_decisive(self):
        # 3 A>B>C, 2 B>A>C, 2 C>A>B: B and C tie for last and are eliminated
        # together, without a tiebreak
        profile = create_ranked_profile(
            ABC, [(3, ["A", "B", "C"]), (2, ["B", "A", "C"]), (2, ["C", "A", "B"])]
        )

        result = outcome("irv", profile)

        assert result.winner == "A"
        assert result.decisive is False

    def test_plurality_tie_is_not_decisive(self):
        profile = create_ranked_profile(ABC, [(1, ["A", "B", "C"]), (1, ["B", "A", "C"])])

        assert outcome("plurality", profile).decisive is False

    def test_clear_win_is_decisive(self):
        profile = create_ranked_profile(ABC, [(2, ["A", "B", "C"]), (1, ["B", "A", "C"])])

        for method in RANKED_METHODS:
            assert outcome(method, profile).decisive is True


class TestWinnerTable:
    @pytest.mark.parametrize("method", RANKED_METHODS)
    def test_lookup_of_pooled_profiles_matches_the_reference(self, method):
        """The consistency search finds pooled profiles by key; check the keys."""
        table = build_winner_table(method, ABC, 8)
        types = rankings(ABC)
        for small in range(1, 5):
            for first in list(profiles(ABC, small))[::5]:
                for second in list(profiles(ABC, 8 - small))[::17]:
                    pooled = combine(first, second)
                    by_ranking = {ranking: count for count, ranking in pooled.rows}
                    counts = np.array([[by_ranking.get(t, 0) for t in types]], dtype=np.int64)

                    reference = outcome(method, pooled)
                    expected = ABC.index(reference.winner) if reference.decisive else -1
                    assert table.lookup(8, counts)[0] == expected


class TestSearch:
    def test_borda_majority_failure_is_found_and_certified(self):
        result = search("borda", "majority", 6)

        assert result.specimen is not None
        certify(result.specimen)
        winner = result.specimen.profile("profile").winner
        assert winner != result.specimen.focus

    def test_no_specimen_is_reported_as_none(self):
        assert search("plurality", "majority", 8).specimen is None

    def test_reports_its_bound(self):
        result = search("ranked_pairs", "condorcet_winner", 5)

        assert (result.max_voters, result.candidates) == (5, ABC)


class TestCommittedArtifacts:
    def test_every_cell_is_searched_once(self):
        cells = [(r["method"], r["criterion"]) for r in committed_searches()]

        assert len(cells) == len(set(cells)) == 32

    @pytest.mark.parametrize(
        "record", committed_specimens(), ids=lambda record: record["id"]
    )
    def test_specimen_certifies_and_round_trips(self, record):
        specimen = specimen_from_json(record)

        certify(specimen)
        assert specimen_to_json(specimen) == record

    @pytest.mark.parametrize(
        "record",
        [r for r in committed_searches() if r["specimen"] and r["specimen"]["voters"] <= 9],
        ids=lambda record: record["specimen"]["id"],
    )
    def test_small_specimens_reproduce(self, record):
        """Searching up to the specimen's size finds exactly that specimen."""
        specimen = specimen_from_json(record["specimen"])

        result = search(specimen.method, specimen.criterion, specimen.voters)

        assert result.specimen == specimen

    def test_presets_match_the_reference_methods(self):
        for preset in load("presets.json")["presets"]:  # type: ignore[union-attr]
            profile = create_ranked_profile(preset["candidates"], preset["rows"])
            for method in RANKED_METHODS:
                result = outcome(method, profile)
                assert result.decisive
                assert result.winner == preset["winners"][method]


class TestCertificationRejects:
    def specimen(self):
        result = search("irv", "condorcet_winner", 6)
        assert result.specimen is not None
        return result.specimen

    def test_wrong_winner(self):
        specimen = self.specimen()
        wrong = dataclasses.replace(
            specimen,
            profiles=(dataclasses.replace(specimen.profiles[0], winner="Z"),),
        )

        with pytest.raises(SpecimenError):
            certify(wrong)

    def test_no_violation(self):
        specimen = self.specimen()
        honest = dataclasses.replace(specimen, focus=specimen.profiles[0].winner)

        with pytest.raises(SpecimenError):
            certify(honest)

    def test_transformation_that_does_not_match(self):
        result = search("plurality", "iia", 8)
        assert result.specimen is not None
        bogus = dataclasses.replace(
            result.specimen, transformation=AddVoters(("A", "B", "C"), 1)
        )

        with pytest.raises(SpecimenError):
            certify(bogus)
