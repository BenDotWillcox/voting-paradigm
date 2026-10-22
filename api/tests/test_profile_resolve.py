"""
HTTP-layer tests for POST /api/voting/profile/resolve.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app

URL = "/api/voting/profile/resolve"
PRESETS = Path(__file__).resolve().parents[2] / "public" / "data" / "methods" / "presets.json"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def request(rows: list[tuple[int, str]], candidates: str = "ABC", **extra) -> dict:
    """Build a request from rows like (6, "ABC")."""
    return {
        "profile": {
            "ballot_type": "ranked",
            "candidates": list(candidates),
            "rows": [{"count": count, "ranking": list(r)} for count, r in rows],
        },
        **extra,
    }


def winners(body: dict) -> dict[str, str]:
    return {result["method"]: result["winner"] for result in body["results"]}


# The tour's opening majority cycle: A over B by 1, B over C by 5, C over A by 3
MAJORITY_CYCLE = [(6, "ABC"), (4, "BCA"), (2, "CAB"), (3, "CBA")]


class TestResolution:
    def test_majority_cycle(self, client: TestClient):
        resp = client.post(URL, json=request(MAJORITY_CYCLE))
        assert resp.status_code == 200
        body = resp.json()

        assert winners(body) == {
            "plurality": "A",
            "irv": "C",
            "borda": "B",
            "ranked_pairs": "B",
        }
        assert all(r["decisive"] and r["tiebreaks"] == [] for r in body["results"])
        assert body["criteria"] == {
            "majority_winner": None,
            "condorcet_winner": None,
            "condorcet_loser": None,
        }
        assert body["total_voters"] == 15
        assert body["pairwise"]["A"]["B"] == 8
        assert body["pairwise"]["B"]["A"] == 7

    def test_traces(self, client: TestClient):
        body = client.post(URL, json=request(MAJORITY_CYCLE)).json()
        traces = {r["method"]: r["trace"] for r in body["results"]}

        assert traces["plurality"] == {"kind": "plurality", "first_choices": {"A": 6, "B": 4, "C": 5}}
        assert [r["eliminated"] for r in traces["irv"]["rounds"]] == [["B"], []]
        assert traces["borda"]["points"] == {"A": 14, "B": 17, "C": 14}
        assert traces["ranked_pairs"]["locked"] == [
            {"winner": "B", "loser": "C", "margin": 5},
            {"winner": "C", "loser": "A", "margin": 3},
        ]
        assert traces["ranked_pairs"]["skipped"] == [{"winner": "A", "loser": "B", "margin": 1}]

    def test_center_squeeze_criteria(self, client: TestClient):
        body = client.post(URL, json=request([(35, "ACB"), (33, "BCA"), (32, "CBA")])).json()

        assert winners(body) == {"plurality": "A", "irv": "B", "borda": "C", "ranked_pairs": "C"}
        assert body["criteria"]["condorcet_winner"] == "C"
        assert body["criteria"]["condorcet_loser"] == "A"
        assert body["criteria"]["majority_winner"] is None

    def test_echoes_the_canonical_profile(self, client: TestClient):
        messy = request([(0, "ABC"), (2, "CBA"), (3, "ACB"), (1, "CBA")])
        tidy = request([(3, "ACB"), (3, "CBA")])

        first = client.post(URL, json=messy).json()
        second = client.post(URL, json=tidy).json()

        assert first["profile"]["rows"] == [
            {"count": 3, "ranking": ["A", "C", "B"]},
            {"count": 3, "ranking": ["C", "B", "A"]},
        ]
        assert first == second


class TestTies:
    THREE_WAY = [(1, "ABC"), (1, "BCA"), (1, "CAB")]

    def test_records_every_tie(self, client: TestClient):
        body = client.post(URL, json=request(self.THREE_WAY)).json()

        for result in body["results"]:
            assert result["decisive"] is False
            assert result["tiebreaks"][0]["tied"] == ["A", "B", "C"]
            assert result["tiebreaks"][0]["chose"] in {"A", "B", "C"}
        ranked_pairs = body["results"][3]
        # The priority order takes one pick per remaining candidate but the last
        assert len(ranked_pairs["tiebreaks"]) == 2
        assert ranked_pairs["trace"]["tiebreak_priority"]

    def test_same_seed_same_response(self, client: TestClient):
        first = client.post(URL, json=request(self.THREE_WAY, tiebreak_seed=7)).json()
        second = client.post(URL, json=request(self.THREE_WAY, tiebreak_seed=7)).json()

        assert first == second

    def test_seed_changes_the_draw(self, client: TestClient):
        drawn = {
            winners(client.post(URL, json=request(self.THREE_WAY, tiebreak_seed=seed)).json())[
                "plurality"
            ]
            for seed in range(20)
        }

        assert len(drawn) > 1

    def test_irv_batch_elimination_is_not_decisive(self, client: TestClient):
        # B and C tie for last and are eliminated together, with no tiebreak
        body = client.post(URL, json=request([(3, "ABC"), (2, "BAC"), (2, "CAB")])).json()
        irv = body["results"][1]

        assert irv["winner"] == "A"
        assert irv["decisive"] is False
        assert irv["tiebreaks"] == []
        assert irv["trace"]["rounds"][0]["eliminated"] == ["B", "C"]


class TestValidation:
    @pytest.mark.parametrize(
        "payload",
        [
            request([(1, "AB")]),  # incomplete ranking
            request([(1, "ABD")]),  # unknown candidate
            request([(1, "AAB")]),  # repeated candidate
        ],
        ids=["incomplete", "unknown", "repeated"],
    )
    def test_invalid_rankings_are_422_with_a_message(self, client: TestClient, payload):
        resp = client.post(URL, json=payload)

        assert resp.status_code == 422
        assert isinstance(resp.json()["detail"], str)

    @pytest.mark.parametrize(
        "payload",
        [
            request([(0, "ABC")]),  # no voters
            request([(10_001, "ABC")]),  # too many voters
            request([(1, "ABCDEF")], candidates="ABCDEF"),  # too many candidates
            request([(1, "A")], candidates="A"),  # too few candidates
            {**request([(1, "ABC")]), "profile": {**request([(1, "ABC")])["profile"], "ballot_type": "approval"}},
            request([(1, ["A b", "B", "C"])], candidates=["A b", "B", "C"]),  # bad candidate id
            request([(1, "ABC")], tiebreak_seed=-1),
        ],
        ids=["no-voters", "too-many-voters", "six-candidates", "one-candidate",
             "unknown-ballot-type", "bad-id", "negative-seed"],
    )
    def test_schema_violations_are_422(self, client: TestClient, payload):
        assert client.post(URL, json=payload).status_code == 422


class TestCommittedPresets:
    def test_preset_resolutions_match_the_live_endpoint(self, client: TestClient):
        """The instrument renders presets from the artifact; it must not drift."""
        presets = json.loads(PRESETS.read_text(encoding="utf-8"))["presets"]

        for preset in presets:
            stored = preset["resolution"]
            live = client.post(
                URL,
                json={"profile": stored["profile"], "tiebreak_seed": stored["tiebreak_seed"]},
            ).json()
            assert live == stored, preset["id"]


class TestOpenAPI:
    def test_documented_under_voting(self, client: TestClient):
        operation = client.get("/openapi.json").json()["paths"][URL]["post"]

        assert operation["tags"] == ["voting"]
        assert operation["summary"] == "Resolve a profile under every ranked method"
        assert "422" in operation["responses"]


def utility_request(rows: list[tuple[int, dict[str, int]]], candidates: str = "ABC", **extra) -> dict:
    return {
        "profile": {
            "ballot_type": "utility",
            "candidates": list(candidates),
            "rows": [{"count": count, "utilities": u} for count, u in rows],
        },
        **extra,
    }


# The center squeeze as voter types: C is a close second for A and B voters
SQUEEZE_TYPES = [
    (35, {"A": 100, "B": 0, "C": 60}),
    (33, {"A": 0, "B": 100, "C": 60}),
    (32, {"A": 0, "B": 40, "C": 100}),
]


class TestUtilityProfiles:
    def test_all_seven_methods(self, client: TestClient):
        body = client.post(URL, json=utility_request(SQUEEZE_TYPES)).json()

        assert winners(body) == {
            "plurality": "A",
            "irv": "B",
            "borda": "C",
            "ranked_pairs": "C",
            "approval": "C",
            "score": "C",
            "quadratic": "C",
        }
        assert body["ballot_model"] == "sincere-v1"
        assert body["rankings"]["rows"] == [
            {"count": 35, "ranking": ["A", "C", "B"]},
            {"count": 33, "ranking": ["B", "C", "A"]},
            {"count": 32, "ranking": ["C", "B", "A"]},
        ]

    def test_each_voter_type_casts_every_format(self, client: TestClient):
        body = client.post(URL, json=utility_request(SQUEEZE_TYPES)).json()
        first = body["voter_ballots"][0]

        assert first == {
            "row": 0,
            "count": 35,
            "choice": "A",
            "ranking": ["A", "C", "B"],
            "approvals": ["A", "C"],
            "scores": {"A": 10, "B": 0, "C": 6},
            # Distances from the mean 53.3 scale to 6.56, -7.49, 0.94 votes
            "allocations": {"A": 7, "B": -7, "C": 1},
            "credits_used": 99,
            "credit_budget": 100,
        }

    def test_rated_traces(self, client: TestClient):
        body = client.post(URL, json=utility_request(SQUEEZE_TYPES)).json()
        traces = {r["method"]: r["trace"] for r in body["results"]}

        assert traces["approval"]["approvals"] == {"A": 35, "B": 33, "C": 100}
        assert traces["score"]["totals"] == {"A": 350, "B": 458, "C": 728}
        assert traces["quadratic"]["credits_available"] == 100 * 100

    def test_rows_keep_their_order_and_are_not_merged(self, client: TestClient):
        rows = [(2, {"A": 0, "B": 50, "C": 100}), (1, {"A": 100, "B": 50, "C": 0}), (1, {"A": 0, "B": 60, "C": 100})]
        body = client.post(URL, json=utility_request(rows)).json()

        assert [r["count"] for r in body["profile"]["rows"]] == [2, 1, 1]
        assert len(body["voter_ballots"]) == 3
        assert body["rankings"]["rows"][-1] == {"count": 3, "ranking": ["C", "B", "A"]}

    def test_ranked_input_has_no_rated_methods(self, client: TestClient):
        body = client.post(URL, json=request(MAJORITY_CYCLE)).json()

        assert [r["method"] for r in body["results"]] == ["plurality", "irv", "borda", "ranked_pairs"]
        assert body["ballot_model"] is None
        assert body["voter_ballots"] == []

    @pytest.mark.parametrize(
        "rows",
        [
            [(1, {"A": 0, "B": 50})],
            [(1, {"A": 0, "B": 50, "C": 101})],
            [(1, {"A": 0, "B": 50, "C": 100, "D": 1})],
        ],
        ids=["missing", "above-scale", "unknown"],
    )
    def test_invalid_utilities_are_422(self, client: TestClient, rows):
        resp = client.post(URL, json=utility_request(rows))

        assert resp.status_code == 422
        assert isinstance(resp.json()["detail"], str)


SPECIMEN_RESOLUTIONS = PRESETS.with_name("specimen-resolutions.json")


class TestCommittedSpecimenResolutions:
    def test_match_the_live_endpoint_and_their_keys(self, client: TestClient):
        """The gallery opens specimens from this file by key; it must not drift."""
        import importlib.util

        script = PRESETS.parents[3] / "scripts" / "build_methods_artifacts.py"
        spec = importlib.util.spec_from_file_location("build_methods_artifacts", script)
        assert spec is not None and spec.loader is not None
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)

        stored = json.loads(SPECIMEN_RESOLUTIONS.read_text(encoding="utf-8"))["resolutions"]
        assert stored
        for key, resolution in stored.items():
            profile = resolution["profile"]
            rows = [(row["count"], row["utilities"]) for row in profile["rows"]]
            assert build.instrument_key(profile["candidates"], rows) == key

            live = client.post(
                URL, json={"profile": profile, "tiebreak_seed": resolution["tiebreak_seed"]}
            ).json()
            assert live == resolution, key

    def test_key_names_candidates_only_when_not_the_first_letters(self):
        import importlib.util

        script = PRESETS.parents[3] / "scripts" / "build_methods_artifacts.py"
        spec = importlib.util.spec_from_file_location("build_methods_artifacts", script)
        assert spec is not None and spec.loader is not None
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)

        assert build.instrument_key(["A", "B"], [(3, {"A": 100, "B": 0})]) == "3:100,0"
        assert build.instrument_key(["A", "C"], [(3, {"A": 100, "C": 0})]) == "AC|3:100,0"
