"""Public comparison endpoint validation, determinism, and response shape."""

import asyncio
from copy import deepcopy
import json

import httpx
import pytest

from api.main import app
from expressive.comparison import ComparisonVoter
from expressive.scalar import ScalarBallot


def payload() -> dict[str, object]:
    return {
        "ballot": {"ideal": 6, "lower_half_width": 2, "upper_half_width": 1.5,
                   "approval_min": 2, "approval_max": 10, "probe": 8},
        "binary_vote": "no",
    }


def request(body: dict[str, object]) -> httpx.Response:
    async def perform() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test",
        ) as client:
            return await client.post(
                "/api/expressive/scalar/compare", content=json.dumps(body),
                headers={"Content-Type": "application/json"},
            )
    return asyncio.run(perform())


def test_response_contract_and_stateless_repeatability() -> None:
    body = payload()
    original = deepcopy(body)
    response = request(body)
    assert response.status_code == 200
    result = response.json()
    assert result["model"] == "scalar-comparison-v4"
    assert result["scenario"] == "prepared"
    assert (result["status_quo"], result["proposal"], result["electorate_size"]) == (4.55, 4.4, 100)
    assert result["candidate_step"] == .05
    assert result["score_tie_tolerance"] == 1e-12
    assert result["user_binary_vote"] == result["user_curve_vote"] == "no"
    assert "scenarios" not in result
    electorate = result["electorate"]
    assert electorate["id"] == "scalar-electorate-v1"
    assert electorate["seed"] == 20221108
    assert len(electorate["voters"]) == len({voter["id"] for voter in electorate["voters"]}) == 100
    assert sum(voter["id"] == "you" for voter in electorate["voters"]) == 1
    assert len(result["points"]) == 2001
    assert all("cohort_scores" not in point for point in result["points"])
    points_by_rate = {point["rate"]: point for point in result["points"]}
    assert result["pair"]["status_quo_mean"] == points_by_rate[4.55]["mean_score"]
    assert result["pair"]["proposal_mean"] == points_by_rate[4.4]["mean_score"]
    for vote in ("yes", "no", "abstain"):
        assert result["binary"][vote] == sum(voter["binary_vote"] == vote for voter in electorate["voters"])
    assert result["binary"]["passed"] == (result["binary"]["yes"] > result["binary"]["no"])
    assert result == request(body).json()
    assert body == original
    assert request(dict(body, scenario="prepared")).json() == result


@pytest.mark.parametrize("scenario", ["prepared", "broad-agreement", "polarized", "intense-minority"])
def test_selected_scenario_is_echoed_and_uses_a_fixed_99(scenario: str) -> None:
    body = dict(payload(), scenario=scenario)
    response = request(body)
    assert response.status_code == 200
    result = response.json()
    assert result["scenario"] == scenario
    assert result["model"] == "scalar-comparison-v4"
    assert len(result["electorate"]["voters"]) == 100
    assert result == request(body).json()
    expected_id = "scalar-electorate-v1" if scenario == "prepared" else f"scalar-electorate-{scenario}-v2"
    assert result["electorate"]["id"] == expected_id
    assert result["electorate"]["seed"] > 0
    assert len({json.dumps(voter["ballot"], sort_keys=True) for voter in result["electorate"]["voters"][:-1]}) == 99
    body["ballot"] = {"ideal": 100, "lower_half_width": 1, "upper_half_width": 1,
                      "approval_min": 100, "approval_max": 100, "probe": 100}
    body["binary_vote"] = "yes"
    changed = request(body).json()
    assert changed["scenario"] == scenario
    assert changed["electorate"]["voters"][:-1] == result["electorate"]["voters"][:-1]
    assert changed["electorate"]["voters"][-1]["ballot"]["ideal"] == 100
    assert changed["user_binary_vote"] == "yes" and changed["user_curve_vote"] == "abstain"
    assert changed["points"][-1]["user_score"] == 1


@pytest.mark.parametrize("scenario", ["", "unknown", None, True, 1, [], {}])
def test_invalid_scenarios_rejected(scenario: object) -> None:
    assert request(dict(payload(), scenario=scenario)).status_code == 422


def test_scenario_response_retains_all_tied_maximizers(monkeypatch: pytest.MonkeyPatch) -> None:
    # Exercise the real HTTP contract with a deliberately tied, hand-authored
    # background rather than coupling the tie rule to one scenario's RNG.
    voters = tuple(ComparisonVoter(
        f"voter-{index + 1:03d}", f"Voter {index + 1}",
        ScalarBallot(3, 0.1, 0.1, 3, 3) if index < 49 else ScalarBallot(5.95, 0.1, 0.1, 5.95, 5.95),
        "yes" if index < 49 else "no",
    ) for index in range(99))
    monkeypatch.setattr("expressive.comparison.scenario_voters", lambda _scenario: voters)
    body = {
        "scenario": "polarized",
        "binary_vote": "yes",
        "ballot": {"ideal": 3, "lower_half_width": 0.1, "upper_half_width": 0.1,
                   "approval_min": 3, "approval_max": 3, "probe": 3},
    }
    response = request(body)
    assert response.status_code == 200
    result = response.json()
    assert result["winner_rates"] == [3, 5.95]
    assert result["binary"]["yes"] == result["binary"]["no"] == 50
    assert result["binary"]["outcome_rate"] == 4.55


def test_probe_never_changes_scores_and_explicit_vote_survives_disagreement() -> None:
    body = payload()
    result = request(body).json()
    body["ballot"] = dict(body["ballot"], probe=13)  # type: ignore[arg-type]
    assert request(body).json() == result
    original = result
    body["binary_vote"] = "yes"
    result = request(body).json()
    assert result["user_binary_vote"] == "yes"
    assert result["user_curve_vote"] == "no"
    assert result["binary"]["yes"] == original["binary"]["yes"] + 1
    assert result["electorate"]["voters"][:-1] == original["electorate"]["voters"][:-1]
    assert result["electorate"]["voters"][-1]["binary_vote"] == "yes"
    assert result["electorate"]["voters"][-1]["curve_vote"] == "no"


@pytest.mark.parametrize("ideal", [0, 75.55, 100])
def test_comparison_supports_the_full_domain(ideal: float) -> None:
    body = payload()
    body["ballot"] = {"ideal": ideal, "lower_half_width": 100, "upper_half_width": 100,
                      "approval_min": 0, "approval_max": 100, "probe": 100}
    response = request(body)
    assert response.status_code == 200
    result = response.json()
    assert result["electorate"]["voters"][-1]["ballot"]["ideal"] == ideal
    assert result["points"][0]["rate"] == 0
    assert result["points"][-1]["rate"] == 100
    at_ideal = next(point for point in result["points"] if point["rate"] == ideal)
    assert at_ideal["user_score"] == 1
    assert at_ideal["user_approved"]


@pytest.mark.parametrize("vote", ["abstain", "", None, True, 1])
def test_invalid_binary_votes_rejected(vote: object) -> None:
    body = payload()
    body["binary_vote"] = vote
    assert request(body).status_code == 422


@pytest.mark.parametrize("changes", [
    {"ideal": 101}, {"ideal": True}, {"ideal": "6"}, {"ideal": float("nan")},
    {"upper_half_width": 0}, {"lower_half_width": float("inf")},
    {"approval_min": 7}, {"approval_max": 5}, {"unexpected": 0},
])
def test_invalid_ballots_rejected_json_safely(changes: dict[str, object]) -> None:
    body = payload()
    body["ballot"] = dict(body["ballot"], **changes)  # type: ignore[arg-type]
    response = request(body)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_missing_and_extra_fields_rejected() -> None:
    body = payload()
    del body["binary_vote"]
    assert request(body).status_code == 422
    body = payload()
    body["unexpected"] = "value"
    assert request(body).status_code == 422


def test_openapi_documents_response_and_example() -> None:
    schema = app.openapi()
    route = schema["paths"]["/api/expressive/scalar/compare"]["post"]
    assert route["tags"] == ["expressive"]
    assert route["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("ScalarComparisonResponse")
    assert schema["components"]["schemas"]["ScalarComparisonRequest"]["examples"]
    request_schema = schema["components"]["schemas"]["ScalarComparisonRequest"]
    response_schema = schema["components"]["schemas"]["ScalarComparisonResponse"]
    assert request_schema["properties"]["scenario"]["default"] == "prepared"
    assert request_schema["properties"]["scenario"]["enum"] == ["prepared", "broad-agreement", "polarized", "intense-minority"]
    assert "scenario" not in request_schema["required"]
    assert "scenario" in response_schema["required"]
