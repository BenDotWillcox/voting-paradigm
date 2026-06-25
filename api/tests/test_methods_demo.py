"""
HTTP-layer tests for the interactive voting-methods demo.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


class TestMethodsDemoScenarios:
    def test_demo_scenarios_list_has_portfolio_set(self, client: TestClient):
        resp = client.get("/api/elections/demo-scenarios")
        assert resp.status_code == 200
        body = resp.json()

        assert [scenario["id"] for scenario in body] == [
            "transportation",
            "energy",
            "parks",
            "budget",
            "cycle",
        ]
        assert all(len(scenario["controls"]) == 5 for scenario in body)
        assert all(scenario["voter_count"] == 100 for scenario in body)

    def test_default_resolution_returns_all_methods(self, client: TestClient):
        scenarios = client.get("/api/elections/demo-scenarios").json()
        transportation = scenarios[0]

        resp = client.post(
            "/api/elections/demo-scenarios/transportation/resolve",
            json={"controls": transportation["default_controls"]},
        )
        assert resp.status_code == 200
        body = resp.json()

        expected_methods = {
            "plurality",
            "approval",
            "irv",
            "borda",
            "ranked_pairs",
            "score",
            "quadratic",
        }
        assert set(body["results"]) == expected_methods
        assert set(body["comparison"]) == expected_methods
        assert body["scenario"]["id"] == "transportation"
        assert sum(bloc["voters"] for bloc in body["scenario"]["blocs"]) == 100
        assert body["annotations"]

    def test_slider_modified_resolution_updates_controls(self, client: TestClient):
        controls = {
            "polarization": 85,
            "compromise": 20,
            "strategy": 75,
            "turnout": 90,
            "intensity": 80,
        }

        resp = client.post(
            "/api/elections/demo-scenarios/energy/resolve",
            json={"controls": controls},
        )
        assert resp.status_code == 200
        body = resp.json()

        assert body["controls"] == controls
        assert len(body["derived_ballots"]["plurality"]) == 100
        assert len(body["derived_ballots"]["ranked"]) == 100
        assert body["comparison"]["irv"]["winner_name"]

    def test_unknown_demo_scenario_returns_404(self, client: TestClient):
        resp = client.post(
            "/api/elections/demo-scenarios/not-real/resolve",
            json={"controls": {}},
        )
        assert resp.status_code == 404
