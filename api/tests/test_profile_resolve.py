"""
HTTP-layer tests for POST /api/voting/profile/resolve.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app

URL = "/api/voting/profile/resolve"


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


class TestOpenAPI:
    def test_documented_under_voting(self, client: TestClient):
        operation = client.get("/openapi.json").json()["paths"][URL]["post"]

        assert operation["tags"] == ["voting"]
        assert operation["summary"] == "Resolve a profile under every ranked method"
        assert "422" in operation["responses"]
