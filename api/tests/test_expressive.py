"""HTTP validation and statelessness for expressive budget previews."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from typing import Any

import httpx
import pytest

from api.main import app
from expressive import CATEGORIES


def payload() -> dict[str, Any]:
    return {
        "ideal": {"roads": 25, "sidewalks": 20, "crossings": 15, "trees": 15, "parks": 15, "facilities": 10},
        "flexibility": {
            category: {"decrease": 10, "increase": 10} for category in CATEGORIES
        },
        "transfers": [
            {"source": "roads", "target": "sidewalks", "amount": 10},
            {"source": "roads", "target": "trees", "amount": 5},
        ],
    }


def request(body: dict[str, Any], *, raw: bool = False) -> httpx.Response:
    async def perform() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            if raw:
                return await client.post(
                    "/api/expressive/budget/preview",
                    content=json.dumps(body),
                    headers={"Content-Type": "application/json"},
                )
            return await client.post("/api/expressive/budget/preview", json=body)
    return asyncio.run(perform())


def test_response_contract_and_independent_transfer_previews() -> None:
    body = payload()
    original = deepcopy(body)
    response = request(body)
    assert response.status_code == 200
    result = response.json()
    assert result["model"] == "neighborhood-budget-v2"
    assert result["fund_id"] == "chicago-neighborhood-fund-v1"
    assert result["fund_total"] == 1_000_000
    first, second = result["previews"]
    assert first["allocation"] == {**body["ideal"], "roads": 15, "sidewalks": 30}
    assert second["allocation"] == {**body["ideal"], "roads": 20, "trees": 20}
    assert first["category_scores"] == {category: .5 if category in ("roads", "sidewalks") else 1 for category in CATEGORIES}
    assert first["feasible"] is True and first["funding_issues"] == []
    assert second["feasible"] is True and second["funding_issues"] == []
    assert first["score"] == .25
    assert second["score"] > first["score"]
    assert body == original
    assert request(body).json() == result


def test_infeasible_transfers_keep_allocations_without_discarding_feasible_previews() -> None:
    body = payload()
    body["transfers"] = [
        {"source": "roads", "target": "trees", "amount": 5},
        {"source": "crossings", "target": "sidewalks", "amount": 5},
        {"source": "roads", "target": "crossings", "amount": 5},
        {"source": "crossings", "target": "sidewalks", "amount": 15},
        {"source": "crossings", "target": "facilities", "amount": 5},
    ]
    response = request(body)
    assert response.status_code == 200
    program, partial, excess, cancel, both = response.json()["previews"]
    assert program["feasible"] is True and program["score"] > 0
    assert partial["allocation"] == {**body["ideal"], "crossings": 10, "sidewalks": 25}
    assert partial["funding_issues"] == [{
        "category": "crossings", "kind": "below_threshold", "required_share": 15, "actual_share": 10,
    }]
    assert excess["funding_issues"] == [{
        "category": "crossings", "kind": "above_cost", "required_share": 15, "actual_share": 20,
    }]
    assert cancel["allocation"]["crossings"] == 0
    assert cancel["feasible"] is True and cancel["score"] > 0 and cancel["funding_issues"] == []
    assert len(both["funding_issues"]) == 2
    for infeasible in (partial, excess, both):
        assert infeasible["feasible"] is False
        assert infeasible["score"] is None and infeasible["category_scores"] is None
        assert sum(infeasible["allocation"].values()) == 100


def test_unfunded_project_can_receive_full_cost_but_not_partial_funding() -> None:
    body = payload()
    body["ideal"].update(crossings=0, roads=40)
    body["transfers"] = [
        {"source": "roads", "target": "crossings", "amount": 15},
        {"source": "roads", "target": "crossings", "amount": 5},
    ]
    response = request(body)
    assert response.status_code == 200
    full, partial = response.json()["previews"]
    assert full["feasible"] is True and full["allocation"]["crossings"] == 15
    assert partial["feasible"] is False and partial["score"] is None


@pytest.mark.parametrize("share", [5, 14.999, 15.001, 20])
def test_infeasible_ideal_is_a_request_error(share: float) -> None:
    body = payload()
    body["ideal"].update(crossings=share, roads=40 - share)
    response = request(body)
    assert response.status_code == 422
    assert "complete cost" in response.json()["detail"][0]["msg"]


@pytest.mark.parametrize("change", [
    "total", "missing_category", "extra_category", "extra_field", "missing_flexibility",
    "zero_width", "negative_share", "bool_share", "same_category", "overdraft",
    "zero_amount", "unknown_category", "empty_transfers", "too_many_transfers", "string_share",
])
def test_rejects_invalid_requests(change: str) -> None:
    body = payload()
    if change == "total": body["ideal"]["roads"] = 24
    elif change == "missing_category": del body["ideal"]["trees"]
    elif change == "extra_category": body["ideal"]["other"] = 0
    elif change == "extra_field": body["not_supported"] = True
    elif change == "missing_flexibility": del body["flexibility"]["trees"]
    elif change == "zero_width": body["flexibility"]["trees"]["increase"] = 0
    elif change == "negative_share": body["ideal"]["trees"] = -1
    elif change == "bool_share": body["ideal"]["trees"] = True
    elif change == "same_category": body["transfers"][0]["target"] = "roads"
    elif change == "overdraft": body["transfers"][0]["amount"] = 26
    elif change == "zero_amount": body["transfers"][0]["amount"] = 0
    elif change == "unknown_category": body["transfers"][0]["target"] = "other"
    elif change == "empty_transfers": body["transfers"] = []
    elif change == "too_many_transfers": body["transfers"] = body["transfers"] * 7
    elif change == "string_share": body["ideal"]["trees"] = "15"
    response = request(body)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("location", ["ideal", "flexibility", "transfer"])
def test_nonfinite_numbers_produce_validation_errors(value: float, location: str) -> None:
    body = payload()
    if location == "ideal": body["ideal"]["trees"] = value
    elif location == "flexibility": body["flexibility"]["trees"]["decrease"] = value
    else: body["transfers"][0]["amount"] = value
    assert request(body, raw=True).status_code == 422


def test_endpoint_is_documented_with_typed_schema_and_example() -> None:
    schema = app.openapi()
    operation = schema["paths"]["/api/expressive/budget/preview"]["post"]
    assert operation["tags"] == ["expressive"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("BudgetPreviewResponse")
    assert schema["components"]["schemas"]["BudgetPreviewRequest"]["examples"]
    example = schema["components"]["schemas"]["BudgetPreviewRequest"]["examples"][0]
    response = request(example)
    assert response.status_code == 200
    assert [preview["feasible"] for preview in response.json()["previews"]] == [True, False, True]
