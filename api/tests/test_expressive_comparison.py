"""Public comparison endpoint validation, determinism, and response shape."""

import asyncio
from copy import deepcopy
import json

import httpx
import pytest

from api.main import app


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
    body["scenario"] = "flexible"
    assert request(body).status_code == 422


def test_openapi_documents_response_and_example() -> None:
    schema = app.openapi()
    route = schema["paths"]["/api/expressive/scalar/compare"]["post"]
    assert route["tags"] == ["expressive"]
    assert route["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("ScalarComparisonResponse")
    assert schema["components"]["schemas"]["ScalarComparisonRequest"]["examples"]
