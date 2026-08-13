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


def make_evidence(question, value=7.5):
    opt_ids = [o["item_id"] for o in question["options"]]
    return {
        "source": "pairwise",
        "item_a": opt_ids[0],
        "item_b": opt_ids[1],
        "value": value,
        "prompt_id": question["id"],
    }


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
    assert data["state"]["model_version"] == "gaussian_linear_v1"


def test_start_session_with_bradley_terry(client):
    r = client.post(
        "/api/preferences/sessions/start",
        json={
            "user_id": "u1",
            "session_id": "s1",
            "target_questions": 5,
            "model": "bradley_terry",
        },
    )
    assert r.status_code == 200
    assert r.json()["state"]["model_version"] == "bradley_terry_laplace_v1"


@pytest.mark.parametrize("model", ["gaussian_linear", "bradley_terry"])
def test_full_session_flow(client, model):
    # Start
    r = client.post(
        "/api/preferences/sessions/start",
        json={
            "user_id": "u1",
            "session_id": "s1",
            "target_questions": 3,
            "model": model,
        },
    )
    assert r.status_code == 200
    state = r.json()["state"]
    question = r.json()["question"]

    # Answer 3 questions
    for i in range(3):
        r = client.post(
            "/api/preferences/sessions/evidence",
            json={
                "state": state,
                "evidence": make_evidence(question),
                "target_questions": 3,
            },
        )
        assert r.status_code == 200
        data = r.json()
        state = data["state"]
        assert len(state["evidence"]) == i + 1
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


def test_bad_evidence_returns_400(client):
    r = client.post(
        "/api/preferences/sessions/start",
        json={"user_id": "u1", "session_id": "s1", "target_questions": 5},
    )
    state = r.json()["state"]

    # item not in the bank
    r = client.post(
        "/api/preferences/sessions/evidence",
        json={
            "state": state,
            "evidence": {
                "source": "pairwise",
                "item_a": "not_a_real_item",
                "item_b": "economic_freedom",
                "value": 5.0,
            },
            "target_questions": 5,
        },
    )
    assert r.status_code == 400


def test_unconfirmed_inferred_evidence_returns_422(client):
    r = client.post(
        "/api/preferences/sessions/start",
        json={"user_id": "u1", "session_id": "s1", "target_questions": 5},
    )
    state = r.json()["state"]
    question = r.json()["question"]
    opt_ids = [o["item_id"] for o in question["options"]]

    r = client.post(
        "/api/preferences/sessions/evidence",
        json={
            "state": state,
            "evidence": {
                "source": "free_text_extraction",
                "item_a": opt_ids[0],
                "item_b": opt_ids[1],
                "value": 5.0,
                "raw_response": "I care much more about the first thing",
            },
            "target_questions": 5,
        },
    )
    assert r.status_code == 422
    assert "free_text_extraction" in str(r.json()["detail"])


def test_inferred_evidence_cannot_be_smuggled_through_client_state(client):
    started = client.post(
        "/api/preferences/sessions/start",
        json={
            "user_id": "u1",
            "session_id": "s1",
            "target_questions": 5,
            "model": "bradley_terry",
        },
    ).json()
    state = started["state"]
    question = started["question"]
    item_a, item_b = [option["item_id"] for option in question["options"]]
    state["evidence"] = [
        {
            "event_id": "evidence_confirmed_one",
            "source": "free_text_extraction",
            "item_a": item_a,
            "item_b": item_b,
            "value": 3.0,
            "metadata": {"phase4_participant_confirmed": True},
        }
    ]

    response = client.post(
        "/api/preferences/sessions/evidence",
        json={
            "state": state,
            "evidence": {
                "source": "pairwise",
                "item_a": item_a,
                "item_b": item_b,
                "value": 5.0,
            },
            "target_questions": 5,
        },
    )

    assert response.status_code == 422
    assert "wire preference state" in str(response.json()["detail"])


def test_client_cannot_self_assert_typed_participant_confirmation(client):
    started = client.post(
        "/api/preferences/sessions/start",
        json={"user_id": "u1", "session_id": "s1", "target_questions": 5},
    ).json()
    state = started["state"]
    question = started["question"]
    item_a, item_b = [option["item_id"] for option in question["options"]]
    state["evidence"] = [
        {
            "event_id": "evidence_forged",
            "source": "free_text_extraction",
            "item_a": item_a,
            "item_b": item_b,
            "value": 3.0,
            "confirmed_by_participant": True,
        }
    ]

    response = client.post(
        "/api/preferences/sessions/evidence",
        json={
            "state": state,
            "evidence": {
                "source": "pairwise",
                "item_a": item_a,
                "item_b": item_b,
                "value": 5.0,
            },
            "target_questions": 5,
        },
    )

    assert response.status_code == 422
    assert "confirmed_by_participant" in str(response.json()["detail"])


def test_structured_evidence_event_id_survives_wire_state_round_trip(client):
    started = client.post(
        "/api/preferences/sessions/start",
        json={"user_id": "u1", "session_id": "s1", "target_questions": 5},
    ).json()
    state = started["state"]
    question = started["question"]
    item_a, item_b = [option["item_id"] for option in question["options"]]
    state["evidence"] = [
        {
            "event_id": "evidence_structured_one",
            "source": "pairwise",
            "item_a": item_a,
            "item_b": item_b,
            "value": 3.0,
        }
    ]

    response = client.post(
        "/api/preferences/sessions/evidence",
        json={
            "state": state,
            "evidence": {
                "source": "pairwise",
                "item_a": item_a,
                "item_b": item_b,
                "value": 5.0,
            },
            "target_questions": 5,
        },
    )

    assert response.status_code == 200
    assert response.json()["state"]["evidence"][0]["event_id"] == (
        "evidence_structured_one"
    )


def test_legacy_state_upgrades_on_the_wire(client):
    """A pre-Evidence state (responses + thurstone_v1) still works."""
    r = client.post(
        "/api/preferences/sessions/start",
        json={"user_id": "u1", "session_id": "s1", "target_questions": 5},
    )
    fresh = r.json()["state"]
    question = r.json()["question"]
    opt_ids = [o["item_id"] for o in question["options"]]

    legacy_state = {
        "user_id": fresh["user_id"],
        "session_id": fresh["session_id"],
        "item_ids": fresh["item_ids"],
        "mu": fresh["mu"],
        "sigma_flat": fresh["sigma_flat"],
        "responses": [
            {
                "question_id": f"q1_{opt_ids[0]}_vs_{opt_ids[1]}",
                "chosen_option_id": opt_ids[0],
                "strength": 6.0,
            }
        ],
        "n_questions_asked": 1,
        "asked_question_ids": [f"q1_{opt_ids[0]}_vs_{opt_ids[1]}"],
        "model_version": "thurstone_v1",
    }

    r = client.post(
        "/api/preferences/sessions/summary",
        json={"state": legacy_state, "target_questions": 5},
    )
    assert r.status_code == 200
    assert r.json()["model_version"] == "gaussian_linear_v1"
