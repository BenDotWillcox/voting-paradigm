"""
HTTP-layer tests for the districting router.

The domain math is exhaustively covered in `districting/tests/`. The job of
these tests is narrower: confirm the route is wired correctly, the request
validation matches the documented bounds, and the response shape is what
clients will see.

Uses FastAPI's TestClient (sync wrapper around httpx) to avoid pulling in
pytest-asyncio for what is currently a single test file. If we add many
more route tests and want async, swap to httpx.AsyncClient + pytest-asyncio.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from districting import US_2020_KNOWN_APPORTIONMENT


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


class TestApportionmentEndpoint:
    def test_default_cap_returns_2020_apportionment(self, client: TestClient):
        """No cap query param defaults to 435 and reproduces the 2020 result."""
        resp = client.get("/api/districting/apportionment")
        assert resp.status_code == 200
        body = resp.json()
        assert body["cap"] == 435
        assert body["apportionment"] == US_2020_KNOWN_APPORTIONMENT
        assert body["total_states"] == 50
        assert body["total_apportionment_population"] == 331_108_434

    def test_explicit_cap_435_matches_known_apportionment(
        self, client: TestClient
    ):
        resp = client.get("/api/districting/apportionment?cap=435")
        assert resp.status_code == 200
        assert resp.json()["apportionment"] == US_2020_KNOWN_APPORTIONMENT

    def test_seats_sum_to_cap_at_anchor_values(self, client: TestClient):
        for cap in [435, 574, 692, 1000, 11037]:
            resp = client.get(f"/api/districting/apportionment?cap={cap}")
            assert resp.status_code == 200, f"cap={cap}: {resp.text}"
            body = resp.json()
            assert body["cap"] == cap
            assert sum(body["apportionment"].values()) == cap

    def test_cap_below_min_rejected(self, client: TestClient):
        """The slider floor of 435 is enforced at the API boundary."""
        resp = client.get("/api/districting/apportionment?cap=434")
        assert resp.status_code == 422

    def test_cap_above_max_rejected(self, client: TestClient):
        """The slider ceiling of 11,037 is enforced at the API boundary."""
        resp = client.get("/api/districting/apportionment?cap=11038")
        assert resp.status_code == 422

    def test_non_integer_cap_rejected(self, client: TestClient):
        resp = client.get("/api/districting/apportionment?cap=abc")
        assert resp.status_code == 422


class TestPrecomputeManifestEndpoint:
    def test_manifest_lists_anchor_jobs(self, client: TestClient):
        resp = client.get("/api/districting/precompute-manifest")
        assert resp.status_code == 200
        body = resp.json()

        assert body["cache_version"] == "bpd-v1"
        assert body["cap_anchors"] == [435, 574, 692, 1000, 11037]
        assert len(body["priority_state_fips"]) == 10
        assert len(body["jobs"]) == 50
        assert body["priority_state_fips"][0] == "20"

    def test_manifest_cache_keys_include_cap_and_seats(self, client: TestClient):
        resp = client.get("/api/districting/precompute-manifest")
        assert resp.status_code == 200
        california_435 = next(
            job
            for job in resp.json()["jobs"]
            if job["state_fips"] == "06" and job["cap"] == 435
        )

        assert california_435["seats"] == 52
        assert california_435["cache_key"] == (
            "bpd-v1/state-06/cap-435/seats-52.json"
        )
        assert california_435["compute_tier"] == "batch-cache"
