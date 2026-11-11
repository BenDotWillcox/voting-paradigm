"""HTTP contracts and JSON-safe input validation for scalar curve previews."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy

import httpx
import pytest

from api.main import app


def payload() -> dict[str, object]:
    return {
        "ideal": 6,
        "lower_half_width": 2,
        "upper_half_width": 3,
        "approval_min": 2,
        "approval_max": 10,
        "probe": 4,
    }


def request(body: dict[str, object], *, raw: bool = False) -> httpx.Response:
    async def perform() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            if raw:
                return await client.post(
                    "/api/expressive/scalar/preview",
                    content=json.dumps(body),
                    headers={"Content-Type": "application/json"},
                )
            return await client.post("/api/expressive/scalar/preview", json=body)
    return asyncio.run(perform())


def test_scalar_contract_and_statelessness() -> None:
    body = payload()
    original = deepcopy(body)
    response = request(body)
    assert response.status_code == 200
    result = response.json()
    assert set(result) == {"model", "points", "probe"}
    assert result["model"] == "clipped-asymmetric-gaussian-v2"
    assert result["probe"] == {"value": 4, "score": .5, "approved": True}
    assert len(result["points"]) == 2001
    assert result["points"][0]["value"] == 0
    assert result["points"][-1]["value"] == 100
    assert all(set(point) == {"value", "unclipped_score"} for point in result["points"])
    assert body == original
    assert request(body).json() == result


def test_clipped_probe_and_unclipped_samples_are_distinct() -> None:
    body = payload()
    body["probe"] = 1
    result = request(body).json()
    assert result["probe"] == {"value": 1, "score": 0, "approved": False}
    assert next(point["unclipped_score"] for point in result["points"] if point["value"] == 1) > 0


@pytest.mark.parametrize("bound", [2, 10])
def test_approval_bounds_are_inclusive(bound: float) -> None:
    body = payload()
    body["probe"] = bound
    result = request(body).json()
    assert result["probe"]["approved"]
    assert result["probe"]["score"] > 0


def test_singleton_band_and_exact_special_points() -> None:
    body = payload()
    body.update({"ideal": 6.123, "approval_min": 6.123, "approval_max": 6.123, "probe": 6.123})
    response = request(body)
    assert response.status_code == 200
    result = response.json()
    assert result["probe"] == {"value": 6.123, "score": 1, "approved": True}
    assert any(point["value"] == 6.123 and point["unclipped_score"] == 1 for point in result["points"])


@pytest.mark.parametrize("ideal", [0, 100])
def test_full_domain_endpoints_and_maximum_widths_are_valid(ideal: float) -> None:
    body = {"ideal": ideal, "lower_half_width": 100, "upper_half_width": 100,
            "approval_min": 0, "approval_max": 100, "probe": 100 - ideal}
    response = request(body)
    assert response.status_code == 200
    result = response.json()
    assert result["probe"] == {"value": 100 - ideal, "score": .5, "approved": True}
    assert len(result["points"]) == 2001


@pytest.mark.parametrize("field", ["ideal", "lower_half_width", "upper_half_width", "approval_min", "approval_max", "probe"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, "6"])
def test_invalid_field_types_and_nonfinite_values_return_422(field: str, value: object) -> None:
    body = payload()
    body[field] = value
    response = request(body, raw=True)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


@pytest.mark.parametrize("changes", [
    {"ideal": -1}, {"probe": 101}, {"lower_half_width": 0}, {"upper_half_width": 101},
    {"approval_min": -1}, {"approval_max": 101}, {"approval_min": 7},
    {"approval_max": 5}, {"unknown": 0},
])
def test_rejects_bounds_and_extra_fields(changes: dict[str, object]) -> None:
    body = payload()
    body.update(changes)
    assert request(body).status_code == 422


def test_missing_field_rejected() -> None:
    body = payload()
    del body["probe"]
    assert request(body).status_code == 422


def test_openapi_documents_scalar_schema_and_example() -> None:
    schema = app.openapi()
    operation = schema["paths"]["/api/expressive/scalar/preview"]["post"]
    assert operation["tags"] == ["expressive"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("ScalarPreviewResponse")
    assert schema["components"]["schemas"]["ScalarPreviewRequest"]["examples"]
