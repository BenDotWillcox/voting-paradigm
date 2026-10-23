"""
HTTP-layer tests for POST /api/voting/atlas and /api/voting/atlas/point.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app

ATLAS_URL = "/api/voting/atlas"
POINT_URL = "/api/voting/atlas/point"
ARTIFACT = Path(__file__).resolve().parents[2] / "public" / "data" / "methods" / "atlas.json"
METHODS = ["plurality", "irv", "borda", "ranked_pairs", "approval", "score", "quadratic"]
SIZE = 64

HUB = [
    {"id": "A", "x": 0.5, "y": 0.26},
    {"id": "B", "x": 0.27, "y": 0.66},
    {"id": "C", "x": 0.73, "y": 0.66},
    {"id": "D", "x": 0.5, "y": 0.53},
]


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def hub(client: TestClient) -> dict:
    resp = client.post(ATLAS_URL, json={"candidates": HUB})
    assert resp.status_code == 200
    return resp.json()


class TestAtlas:
    def test_one_map_per_method_covering_the_grid(self, hub):
        assert hub["size"] == SIZE
        assert [m["method"] for m in hub["maps"]] == METHODS
        for map_ in hub["maps"]:
            assert len(map_["winners"]) == SIZE * SIZE
            assert set(map_["winners"]) <= set("ABCD")
            assert all(0 <= cell < SIZE * SIZE for cell in map_["ties"])

    def test_reference_maps(self, hub):
        assert set(hub["condorcet"]) <= set("ABCD-")
        assert set(hub["utilitarian"]) <= set("ABCD")
        assert set(hub["disagreement"]) <= set("1234")
        assert len(hub["condorcet"]) == len(hub["utilitarian"]) == len(hub["disagreement"]) == SIZE * SIZE

    def test_describes_its_electorate(self, hub):
        cloud = hub["cloud"]

        assert (len(cloud["offsets"]), cloud["voters_per_type"], cloud["spread"]) == (19, 5, 0.16)
        assert hub["ballot_model"] == "sincere-v1"
        assert hub["tiebreak_seed"] == 0

    @pytest.mark.parametrize(
        "candidates",
        [
            HUB[:2],
            HUB + [{"id": "E", "x": 0.1, "y": 0.1}, {"id": "A", "x": 0.9, "y": 0.9}],
            [HUB[0], HUB[1], {**HUB[2], "id": "A"}],
            [HUB[0], HUB[1], {**HUB[2], "x": 1.5}],
            [HUB[0], HUB[1], {**HUB[2], "id": "Z"}],
        ],
        ids=["two", "six", "repeated", "outside", "unknown-letter"],
    )
    def test_invalid_layouts_are_422(self, client, candidates):
        assert client.post(ATLAS_URL, json={"candidates": candidates}).status_code == 422


class TestPoint:
    @pytest.mark.parametrize("cell", [0, 1000, 2080, 2601, SIZE * SIZE - 1])
    def test_matches_the_map_cell(self, client, hub, cell):
        """The instrument loads exactly the electorate the map counted."""
        body = client.post(POINT_URL, json={"candidates": HUB, "cell": cell}).json()

        assert len(body["profile"]["rows"]) == 19
        assert body["total_voters"] == 95
        by_method = {r["method"]: r for r in body["results"]}
        for map_ in hub["maps"]:
            result = by_method[map_["method"]]
            assert result["winner"] == map_["winners"][cell]
            assert result["decisive"] == (cell not in map_["ties"])
        assert (body["criteria"]["condorcet_winner"] or "-") == hub["condorcet"][cell]

    def test_resolves_like_profile_resolve(self, client):
        point = client.post(POINT_URL, json={"candidates": HUB, "cell": 1234}).json()
        direct = client.post(
            "/api/voting/profile/resolve", json={"profile": point["profile"], "tiebreak_seed": 0}
        ).json()

        assert point == direct

    def test_cell_outside_the_grid_is_422(self, client):
        resp = client.post(POINT_URL, json={"candidates": HUB, "cell": SIZE * SIZE})

        assert resp.status_code == 422


class TestCommittedAtlas:
    def test_layouts_match_the_live_endpoint(self, client):
        """The atlas renders curated layouts from this file; it must not drift."""
        layouts = json.loads(ARTIFACT.read_text(encoding="utf-8"))["layouts"]

        assert [layout["id"] for layout in layouts] == ["hub", "squeeze", "clones", "ring", "spread"]
        for layout in layouts:
            stored = layout["atlas"]
            live = client.post(
                ATLAS_URL,
                json={"candidates": stored["candidates"], "tiebreak_seed": stored["tiebreak_seed"]},
            ).json()
            assert live == stored, layout["id"]


def layout(layout_id: str) -> dict:
    layouts = json.loads(ARTIFACT.read_text(encoding="utf-8"))["layouts"]
    return next(entry["atlas"] for entry in layouts if entry["id"] == layout_id)


def outright(atlas: dict, method: str, candidate: str) -> float:
    """Percent of cells the method gives the candidate without a tiebreak."""
    map_ = next(m for m in atlas["maps"] if m["method"] == method)
    ties = set(map_["ties"])
    won = sum(1 for cell, w in enumerate(map_["winners"]) if w == candidate and cell not in ties)
    return 100 * won / len(map_["winners"])


def tied(atlas: dict, method: str) -> float:
    map_ = next(m for m in atlas["maps"] if m["method"] == method)
    return 100 * len(map_["ties"]) / len(map_["winners"])


def condorcet(atlas: dict, candidate: str) -> float:
    return 100 * atlas["condorcet"].count(candidate) / len(atlas["condorcet"])


class TestCuratedClaims:
    """Each claim in the layout captions (lib/methods/atlas.ts) holds."""

    def test_hub(self):
        hub = layout("hub")

        assert 10.5 <= condorcet(hub, "D") < 11.5
        assert outright(hub, "plurality", "D") < 3
        assert 6.5 <= outright(hub, "irv", "D") < 7.5
        for method in ("borda", "score", "quadratic"):
            assert 12 <= outright(hub, method, "D") < 14
        assert 60.5 <= outright(hub, "approval", "D") < 61.5
        approval = next(m for m in hub["maps"] if m["method"] == "approval")
        # A tiebreak picks among the tied, so D led every tied cell
        assert {approval["winners"][cell] for cell in approval["ties"]} == {"D"}
        assert outright(hub, "approval", "D") + tied(hub, "approval") == pytest.approx(100)

    def test_squeeze(self):
        squeeze = layout("squeeze")

        assert 19.5 <= condorcet(squeeze, "C") < 20.5
        assert 8.5 <= outright(squeeze, "plurality", "C") < 9.5
        assert 16.5 <= outright(squeeze, "irv", "C") < 17.5
        assert 54.5 <= outright(squeeze, "approval", "C") < 55.5

    def test_clones(self):
        clones = layout("clones")

        assert 0.5 <= outright(clones, "plurality", "A") - condorcet(clones, "A") < 1.5
        assert 3.5 <= condorcet(clones, "A") - outright(clones, "borda", "A") < 4.5

    def test_ring(self):
        ring = layout("ring")

        assert 8.5 <= tied(ring, "irv") < 9.5
        assert 17.5 <= tied(ring, "approval") < 18.5
        assert tied(ring, "ranked_pairs") < 0.5

    def test_spread(self):
        spread = layout("spread")
        cells = len(spread["condorcet"])

        for map_ in spread["maps"]:
            for candidate in "ABC":
                share = 100 * map_["winners"].count(candidate) / cells
                assert abs(share - condorcet(spread, candidate)) < 2, map_["method"]
        assert 100 * spread["disagreement"].count("1") / cells >= 96.5
