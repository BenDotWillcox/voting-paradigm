"""Integration tests for the preferences FastAPI endpoints."""

import pytest

try:
    from fastapi.testclient import TestClient
    from api.main import app
except ImportError:
    pytest.skip("FastAPI not available", allow_module_level=True)


@pytest.fixture
def client():
    return TestClient(app)


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_list_items(client):
    r = client.get("/api/preferences/items")
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) > 10
    assert "domains" in data


def test_start_session(client):
    r = client.post(
        "/api/preferences/sessions/start",
        json={"user_id": "u1", "session_id": "s1", "target_questions": 5},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["target_questions"] == 5
    assert data["question"]["question_type"] == "pairwise"
    assert len(data["question"]["options"]) == 2
    assert data["state"]["n_questions_asked"] == 0


def test_full_session_flow(client):
    # Start
    r = client.post(
        "/api/preferences/sessions/start",
        json={"user_id": "u1", "session_id": "s1", "target_questions": 3},
    )
    assert r.status_code == 200
    state = r.json()["state"]
    question = r.json()["question"]

    # Answer 3 questions
    for i in range(3):
        opt_ids = [o["item_id"] for o in question["options"]]
        r = client.post(
            "/api/preferences/sessions/respond",
            json={
                "state": state,
                "response": {
                    "question_id": question["id"],
                    "chosen_option_id": opt_ids[0],
                    "strength": 7.5,
                },
                "question_options": opt_ids,
                "target_questions": 3,
            },
        )
        assert r.status_code == 200
        data = r.json()
        state = data["state"]
        if i < 2:
            assert data["next_question"] is not None
            question = data["next_question"]
        else:
            assert data["next_question"] is None
            assert data["progress"]["is_complete"]

    # Get summary
    r = client.post(
        "/api/preferences/sessions/summary",
        json={"state": state, "target_questions": 3},
    )
    assert r.status_code == 200
    summary = r.json()
    assert summary["progress"]["is_complete"]
    assert len(summary["values"]) >= 2
    # Values are ranked
    means = [v["mean"] for v in summary["values"]]
    assert means == sorted(means, reverse=True)


def test_bad_response_returns_400(client):
    r = client.post(
        "/api/preferences/sessions/start",
        json={"user_id": "u1", "session_id": "s1", "target_questions": 5},
    )
    state = r.json()["state"]
    question = r.json()["question"]
    opt_ids = [o["item_id"] for o in question["options"]]

    # chosen_option_id not in question_options
    r = client.post(
        "/api/preferences/sessions/respond",
        json={
            "state": state,
            "response": {
                "question_id": question["id"],
                "chosen_option_id": "not_a_real_item",
                "strength": 5.0,
            },
            "question_options": opt_ids,
            "target_questions": 5,
        },
    )
    assert r.status_code == 400
