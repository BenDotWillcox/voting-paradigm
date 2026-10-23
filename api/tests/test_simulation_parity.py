"""
The methods simulation counts each election exactly as
POST /api/voting/profile/resolve does.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from eval.methods_simulation import METHODS, SimulationConfig, election_rng, run_election
from voting.spatial import sample_spatial_election

URL = "/api/voting/profile/resolve"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize("candidates", [3, 4, 5])
def test_sampled_elections_match_profile_resolve(client, candidates):
    config = SimulationConfig()
    for index in range(0, 400, 40):
        election = sample_spatial_election(
            election_rng(config, candidates, index), config.voters, candidates
        )
        record = run_election(config, candidates, index)
        ids = list(election.candidates)
        body = client.post(
            URL,
            json={
                "profile": {
                    "ballot_type": "utility",
                    "candidates": ids,
                    "rows": [
                        {"count": count, "utilities": dict(zip(ids, utilities))}
                        for count, utilities in election.profile.rows
                    ],
                },
                "tiebreak_seed": config.tiebreak_seed,
            },
        ).json()

        results = {r["method"]: r for r in body["results"]}
        for i, method in enumerate(METHODS):
            assert results[method]["winner"] == record.winners[i], (index, method)
            assert results[method]["decisive"] == record.decisive[i], (index, method)
        assert body["criteria"]["condorcet_winner"] == record.condorcet
