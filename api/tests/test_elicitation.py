"""Spectrum answers stay descriptive, independent, and unsaved."""

import ast
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.main import app
from api.schemas import elicitation as schemas
from api.services import elicitation
from preferences import spectrum


BANK_VERSION = "spectrum_demo_v1"
QUESTION_IDS = [
    "library_closing_hour",
    "field_booking_share",
    "public_comment_days",
    "facility_booking_weeks",
]


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def record(index, action="answer", **fields):
    response = {
        "action": action,
        "question_id": QUESTION_IDS[index],
        "question_version": 1,
    }
    if action == "answer":
        response["position"] = [20, 50, 28, 6][index]
    return {**response, **fields}


def request(client, responses=()):
    return client.post(
        "/api/preferences/elicitation",
        json={"bank_version": BANK_VERSION, "responses": list(responses)},
    )


def test_initial_session_exposes_questions_but_no_inferred_values(client):
    response = request(client)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert set(data) == {
        "bank_version", "questions", "responses", "n_reviewed", "n_answered",
        "n_skipped", "n_depends", "target_questions", "is_complete",
    }
    assert data["bank_version"] == BANK_VERSION
    assert data["responses"] == []
    assert data["n_reviewed"] == data["n_answered"] == 0
    assert data["n_skipped"] == data["n_depends"] == 0
    assert data["target_questions"] == 4
    assert data["is_complete"] is False
    assert [question["id"] for question in data["questions"]] == QUESTION_IDS


def test_public_questions_use_explicit_quantitative_scales():
    bank = spectrum.load_spectrum_bank()
    assert [
        (question.scale.min, question.scale.max, question.scale.step)
        for question in bank.questions
    ] == [(17, 22, 1), (0, 100, 10), (7, 56, 1), (1, 12, 1)]
    assert [question.scale.unit for question in bank.questions] == [
        "local time", "%", "days", "weeks",
    ]
    for question in bank.questions:
        assert "hypothetical" in question.context.lower()
        assert question.version == 1
        assert question.scale.anchors[0].value == question.scale.min
        assert question.scale.anchors[-1].value == question.scale.max


@pytest.mark.parametrize("count", range(5))
def test_every_prefix_returns_the_answer_summary_without_a_completion_gate(
    client, count
):
    history = [
        record(0, reported_uncertainty={"sd_fraction": 0.08}),
        record(1, "depends"),
        record(2, "skip"),
        record(3, acceptable_range={"lower": 3, "upper": 9}),
    ][:count]
    response = request(client, history)
    assert response.status_code == 200
    data = response.json()
    assert data["n_reviewed"] == count
    for action, count_field in [
        ("answer", "n_answered"), ("skip", "n_skipped"), ("depends", "n_depends")
    ]:
        assert data[count_field] == sum(item["action"] == action for item in history)
    assert len(data["questions"]) == 4
    assert len(data["responses"]) == count
    assert data["is_complete"] is (count == 4)
    for original, returned in zip(history, data["responses"]):
        assert all(returned[key] == value for key, value in original.items())
        if original["action"] != "answer":
            assert returned == original


@pytest.mark.parametrize("explicit_null", [False, True])
def test_optional_reports_are_not_fabricated(client, explicit_null):
    answer = record(0)
    if explicit_null:
        answer.update(reported_uncertainty=None, acceptable_range=None)
    response = request(client, [answer])
    assert response.status_code == 200
    assert response.json()["responses"] == [
        {**record(0), "reported_uncertainty": None, "acceptable_range": None}
    ]


@pytest.mark.parametrize("uncertainty", [
    None, {"sd_fraction": 0.08}, {"sd_fraction": 0.17363}, {"sd_fraction": 0.28},
])
@pytest.mark.parametrize(
    "acceptable_range",
    [None, {"lower": 1, "upper": 12}, {"lower": 8, "upper": 9},
     {"lower": 6, "upper": 6}],
)
def test_uncertainty_and_acceptance_do_not_change_position_or_each_other(
    client, uncertainty, acceptable_range
):
    history = [record(index, "skip") for index in range(3)] + [
        record(3, position=6, reported_uncertainty=uncertainty,
               acceptable_range=acceptable_range)
    ]
    response = request(client, history)
    assert response.status_code == 200
    answer = response.json()["responses"][-1]
    assert answer["position"] == 6
    assert answer["reported_uncertainty"] == uncertainty
    assert answer["acceptable_range"] == acceptable_range


def test_continuous_uncertainty_fraction_is_preserved_on_every_axis(client):
    uncertainty = {"sd_fraction": 0.143726}
    history = [
        record(index, reported_uncertainty=uncertainty) for index in range(4)
    ]
    response = request(client, history)
    assert response.status_code == 200
    assert [item["reported_uncertainty"] for item in response.json()["responses"]] == [
        uncertainty
    ] * 4


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize("endpoint", ["min", "max"])
def test_every_scale_accepts_its_endpoints(client, index, endpoint):
    scale = spectrum.load_spectrum_bank().questions[index].scale
    value = getattr(scale, endpoint)
    response = request(client, [record(i, "skip") for i in range(index)] + [
        record(index, position=value, acceptable_range={"lower": value, "upper": value})
    ])
    assert response.status_code == 200
    assert response.json()["responses"][-1]["position"] == value


def test_zero_and_middle_positions_are_explicit_answers(client):
    for position in (0, 50):
        response = request(client, [record(0, "skip"), record(1, position=position)])
        assert response.status_code == 200
        assert response.json()["n_answered"] == 1
        assert response.json()["responses"][-1]["position"] == position


@pytest.mark.parametrize("position", [8, 29])
def test_public_comment_position_and_acceptable_bounds_have_daily_precision(
    client, position
):
    answer = record(
        2, position=position, acceptable_range={"lower": 8, "upper": 29}
    )
    response = request(client, [record(0, "skip"), record(1, "skip"), answer])
    assert response.status_code == 200
    returned = response.json()["responses"][-1]
    assert returned["position"] == position
    assert returned["acceptable_range"] == {"lower": 8, "upper": 29}


def test_all_nonanswers_have_no_position_uncertainty_or_range(client):
    history = [record(index, ["skip", "depends"][index % 2]) for index in range(4)]
    response = request(client, history)
    assert response.status_code == 200
    data = response.json()
    assert data["responses"] == history
    assert data["n_answered"] == 0
    assert data["n_skipped"] == data["n_depends"] == 2
    assert data["is_complete"] is True


def test_replay_is_deterministic_and_no_session_or_answer_is_retained(client):
    history = [record(0, reported_uncertainty={"sd_fraction": 0.28})]
    before = request(client).json()
    first = request(client, history)
    after = request(client).json()
    second = request(client, history)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert before == after
    assert after["responses"] == []


@pytest.mark.parametrize("mutation", ["invented", "duplicate", "reordered", "gap"])
def test_response_history_must_be_a_fixed_question_prefix(client, mutation):
    history = [record(index) for index in range(3)]
    if mutation == "invented":
        history[0]["question_id"] = "private_marker_never_echo"
    elif mutation == "duplicate":
        history[1] = history[0]
    elif mutation == "gap":
        history.pop(1)
    else:
        history[0], history[1] = history[1], history[0]
    response = request(client, history)
    assert response.status_code == 400
    assert response.json() == {"detail": "response history does not match this session"}
    assert response.headers["cache-control"] == "no-store"
    assert "private_marker" not in response.text


@pytest.mark.parametrize("index,value", [(0, 16), (0, 23), (0, 20.5), (1, 55),
                                          (2, 8.5), (3, 6.000000000000001)])
@pytest.mark.parametrize("field", ["position", "lower", "upper"])
def test_positions_and_acceptance_must_match_the_question_grid(
    client, index, value, field
):
    scale = spectrum.load_spectrum_bank().questions[index].scale
    fields = {"position": value} if field == "position" else {
        "acceptable_range": {
            "lower": min(value, scale.min), "upper": max(value, scale.max),
            field: value,
        }
    }
    response = request(client, [record(i, "skip") for i in range(index)] + [
        record(index, **fields)
    ])
    assert response.status_code == 400
    assert response.json() == {
        "detail": "response values must match the question scale"
    }
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("answer", [
    {"action": "answer", "question_id": QUESTION_IDS[0], "question_version": 1},
    record(0, position="20"), record(0, position=True),
    record(0, reported_uncertainty=0.8), record(0, reported_uncertainty="certain"),
    record(0, reported_uncertainty="broad"),
    record(0, reported_uncertainty="moderate"),
    record(0, reported_uncertainty="narrow"),
    record(0, reported_uncertainty={}),
    record(0, reported_uncertainty={"sd_fraction": 0.079999}),
    record(0, reported_uncertainty={"sd_fraction": 0.280001}),
    record(0, reported_uncertainty={"sd_fraction": "0.18"}),
    record(0, reported_uncertainty={"sd_fraction": True}),
    record(0, reported_uncertainty={"sd_fraction": None}),
    record(0, reported_uncertainty={"sd_fraction": 0.18, "confidence": 0.8}),
    record(0, acceptable_range={"lower": 22, "upper": 17}),
    record(0, acceptable_range={"lower": "17", "upper": 22}),
    record(0, acceptable_range={"lower": 17}),
    record(0, question_version=2), record(0, question_version="1"),
    record(0, question_version=True), record(0, question_version=1.0),
    record(0, "skip", position=20), record(0, "depends", reported_uncertainty=None),
    record(0, value=0), record(0, notes="private_marker_never_echo"),
])
def test_malformed_answers_are_sanitized_at_the_request_boundary(client, answer):
    response = request(client, [answer])
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid elicitation request."}
    assert response.headers["cache-control"] == "no-store"
    assert "private_marker" not in response.text


@pytest.mark.parametrize("payload", [
    {}, {"model": "gaussian_linear"}, {"bank_version": "spectrum_demo_v0"},
    {"bank_version": BANK_VERSION, "model": "bradley_terry"},
    {"bank_version": BANK_VERSION, "state": {"mu": [9.0]}},
    {"bank_version": BANK_VERSION, "responses": [record(0, "skip")] * 5},
])
def test_old_model_payloads_and_unversioned_sessions_are_rejected(client, payload):
    response = client.post("/api/preferences/elicitation", json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid elicitation request."}


@pytest.mark.parametrize("raw_number", ["NaN", "Infinity", "-Infinity", "1e400"])
@pytest.mark.parametrize("field", ["position", "lower", "upper", "sd_fraction"])
def test_nonfinite_http_values_never_echo_payloads(client, raw_number, field):
    answer = record(0, question_id="private_marker_never_echo")
    if field == "position":
        answer[field] = "REPLACE_NUMBER"
    elif field == "sd_fraction":
        answer["reported_uncertainty"] = {"sd_fraction": "REPLACE_NUMBER"}
    else:
        answer["acceptable_range"] = {"lower": 17, "upper": 22, field: "REPLACE_NUMBER"}
    body = json.dumps({"bank_version": BANK_VERSION, "responses": [answer]})
    response = client.post(
        "/api/preferences/elicitation",
        content=body.replace('"REPLACE_NUMBER"', raw_number),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid elicitation request."}
    assert response.headers["cache-control"] == "no-store"
    assert "private_marker" not in response.text


def test_malformed_json_does_not_echo_response_content(client):
    response = client.post(
        "/api/preferences/elicitation",
        content='{"responses":"private_marker_never_echo"',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid elicitation request."}


def test_other_routes_keep_their_existing_contracts_and_errors(client):
    valid = client.post(
        "/api/preferences/sessions/start",
        json={"user_id": "test", "session_id": "test", "model": "gaussian_linear"},
    )
    assert valid.status_code == 200
    assert valid.json()["state"]["model_version"] == "gaussian_linear_v1"
    invalid = client.post(
        "/api/preferences/sessions/start",
        json={"user_id": "test", "session_id": "test", "model": "unknown"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"][0]["loc"] == ["body", "model"]
    assert "cache-control" not in invalid.headers


def test_question_bank_is_immutable():
    question = spectrum.load_spectrum_bank().questions[0]
    with pytest.raises(ValidationError, match="frozen"):
        question.scale.anchors[0].label = "Changed"


def test_service_uses_only_public_bank_and_never_logs_answers(monkeypatch, caplog):
    original_read = Path.read_text
    reads = []

    def checked_read(path, *args, **kwargs):
        reads.append(path.resolve())
        assert path.resolve() == spectrum.PUBLIC_SPECTRUM_BANK_PATH.resolve()
        return original_read(path, *args, **kwargs)

    spectrum.load_spectrum_bank.cache_clear()
    with monkeypatch.context() as context:
        context.setattr(Path, "read_text", checked_read)
        result = elicitation.run_elicitation(
            schemas.ElicitationRequest.model_validate(
                {"bank_version": BANK_VERSION, "responses": [record(0)]}
            )
        )
    assert result.n_answered == 1
    assert reads == [spectrum.PUBLIC_SPECTRUM_BANK_PATH.resolve()]
    assert caplog.records == []


def test_spectrum_path_does_not_import_evaluation_or_statistical_models():
    for module in (spectrum, schemas, elicitation):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imports = [
            node.module for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        ] + [
            alias.name for node in ast.walk(tree)
            if isinstance(node, ast.Import) for alias in node.names
        ]
        for name in imports:
            assert not name.startswith((
                "eval", "preferences.model", "preferences.acquisition", "numpy", "scipy"
            ))
