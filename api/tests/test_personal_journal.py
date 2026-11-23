import json
from copy import deepcopy

import httpx
import pytest
from fastapi.testclient import TestClient

from api.main import app
from preferences import journal_forecast


PATH = "/api/preferences/journal/forecast"
HEADERS = {"X-Journal-Token": "local-test-token"}
MEASURE = {
    "title": "Library extension",
    "sourceUrl": "https://example.org/ballot/01",
    "text": "The proposed levy would fund an extension of library hours.",
    "yesMeaning": "Extend library hours through Saturday.",
    "noMeaning": "Keep libraries closed on weekends.",
    "familiar": False,
}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("PERSONAL_JOURNAL_LOCAL", "1")
    monkeypatch.setenv("PERSONAL_JOURNAL_API_TOKEN", HEADERS["X-Journal-Token"])
    monkeypatch.delenv("NODE_ENV", raising=False)
    monkeypatch.delenv("PERSONAL_JOURNAL_MODEL_MODE", raising=False)
    monkeypatch.delenv("PREFERENCE_LLM_BASE_URL", raising=False)
    return TestClient(app, client=("127.0.0.1", 7921))


def packet():
    return {
        "id": "00000000-0000-4000-8000-000000000001",
        "measure": deepcopy(MEASURE), "history": [],
    }


def earlier(vote="yes"):
    return {"measure": deepcopy(MEASURE), "vote": vote, "reasoning": "I use the library on weekends."}


def forecast(client, data):
    response = client.post(PATH, headers=HEADERS, json=data)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_empty_history_and_changed_or_reversed_choices(client):
    req = packet()
    cold = forecast(client, req)
    assert set(cold) == {"choice", "probabilityYes", "model", "explanation", "historyCount"}
    assert cold["probabilityYes"] == 0.5 and cold["historyCount"] == 0
    assert forecast(client, req) == cold
    req["history"] = [earlier()]
    supporting = forecast(client, req)
    assert supporting["probabilityYes"] == pytest.approx(2 / 3, abs=1e-6)
    assert supporting["choice"] == "yes" and supporting["historyCount"] == 1
    req["history"][0]["vote"] = "no"
    opposing = forecast(client, req)
    assert opposing["choice"] == "no"
    assert opposing["probabilityYes"] == pytest.approx(1 - supporting["probabilityYes"])
    req["measure"]["yesMeaning"], req["measure"]["noMeaning"] = req["measure"]["noMeaning"], req["measure"]["yesMeaning"]
    assert forecast(client, req)["probabilityYes"] == supporting["probabilityYes"]
    assert forecast(client, packet()) == cold


def test_unrelated_wording_offers_no_evidence(client):
    req = packet()
    req["history"] = [earlier()]
    req["measure"].update(yesMeaning="Install photovoltaic panels", noMeaning="Continue burning gas")
    assert forecast(client, req)["probabilityYes"] == 0.5


def test_ballot_label_boilerplate_does_not_supply_preference_evidence(client):
    req = packet()
    prior = earlier()
    prior["measure"].update(yesMeaning="A YES vote would repair bridges", noMeaning="A NO vote would defer maintenance")
    req["history"] = [prior]
    req["measure"].update(yesMeaning="A YES vote would fund daycare", noMeaning="A NO vote would cut subsidies")
    assert forecast(client, req)["probabilityYes"] == 0.5


@pytest.mark.parametrize("level", ["top", "measure", "history"])
def test_current_vote_is_not_an_input_or_reflected_in_errors(client, level):
    req = packet()
    req["history"] = [earlier()]
    target = {"top": req, "measure": req["measure"], "history": req["history"][0]}[level]
    target["actualVote"] = "private-invalid-answer"
    response = client.post(PATH, headers=HEADERS, json=req)
    assert response.status_code == 422
    assert "private-invalid-answer" not in response.text


def test_private_route_requires_launcher_loopback_and_token(client, monkeypatch):
    assert client.post(PATH, json=packet()).status_code == 403
    outside = TestClient(app, client=("192.0.2.123", 7921))
    assert outside.post(PATH, headers=HEADERS, json=packet()).status_code == 403
    monkeypatch.setenv("NODE_ENV", "production")
    assert client.post(PATH, headers=HEADERS, content=b"bad-json").status_code == 404
    monkeypatch.delenv("NODE_ENV")
    monkeypatch.delenv("PERSONAL_JOURNAL_LOCAL")
    assert client.post(PATH, headers=HEADERS, json=packet()).status_code == 404
    monkeypatch.setenv("PERSONAL_JOURNAL_LOCAL", "1")
    monkeypatch.delenv("PERSONAL_JOURNAL_API_TOKEN")
    assert client.post(PATH, headers=HEADERS, json=packet()).status_code == 404


def mock_provider(monkeypatch, handler):
    real_client = httpx.Client
    def local_client(**options):
        assert options["trust_env"] is False
        assert options["follow_redirects"] is False
        return real_client(transport=httpx.MockTransport(handler), **options)
    monkeypatch.setattr(journal_forecast.httpx, "Client", local_client)
    monkeypatch.setenv("PERSONAL_JOURNAL_MODEL_MODE", "llm")
    monkeypatch.setenv("PREFERENCE_LLM_MODEL", "fixture-model")


def test_local_llm_receives_prior_reasoning_and_current_packet(client, monkeypatch):
    req = packet()
    req["history"] = [earlier()]
    def handler(request):
        assert str(request.url) == "http://127.0.0.1:11434/v1/chat/completions"
        messages = json.loads(request.content)["messages"]
        data = json.loads(messages[-1]["content"])
        assert data["earlierDecisions"][0]["reasoning"] == req["history"][0]["reasoning"]
        assert data["currentMeasure"] == {key: MEASURE[key] for key in ["title", "text", "yesMeaning", "noMeaning"]}
        prediction = json.dumps({"probabilityYes": 0.8, "explanation": "Earlier weekend choices align."})
        return httpx.Response(200, json={"choices": [{"message": {"content": prediction}}]})
    mock_provider(monkeypatch, handler)
    result = forecast(client, req)
    assert result == {"choice": "yes", "probabilityYes": 0.8, "model": "local-llm-v1/fixture-model",
                      "explanation": "Earlier weekend choices align.", "historyCount": 1}


@pytest.mark.parametrize("url", ["https://example.org/v1", "http://localhost@not-local.invalid/v1", "file://localhost/"])
def test_llm_refuses_nonlocal_destinations(client, monkeypatch, url):
    monkeypatch.setenv("PREFERENCE_LLM_BASE_URL", url)
    mock_provider(monkeypatch, lambda _: pytest.fail("External provider request"))
    response = client.post(PATH, headers=HEADERS, json=packet())
    assert response.status_code == 502


@pytest.mark.parametrize("reply", ["redirect", "malformed", "offline"])
def test_provider_failures_do_not_silently_use_the_wording_baseline(client, monkeypatch, reply):
    destinations = []
    def handler(request):
        destinations.append(request.url.host)
        if reply == "redirect":
            return httpx.Response(307, headers={"Location": "https://example.org"})
        if reply == "offline":
            raise httpx.ConnectError("offline")
        return httpx.Response(200, json={"choices": [{"message": {"content": "private garbage"}}]})
    mock_provider(monkeypatch, handler)
    response = client.post(PATH, headers=HEADERS, json=packet())
    assert response.status_code == 502
    assert "private garbage" not in response.text
    assert destinations == ["127.0.0.1"]


def test_recent_decisions_preserve_order_and_full_newest_receipt():
    history = [journal_forecast.PastDecision(**earlier()) for _ in range(4)]
    for index, decision in enumerate(history):
        decision.reasoning = f"because {index}"
    newest = journal_forecast._recent_decisions(history, budget=1)
    assert [item["reasoning"] for item in newest] == ["because 3"]
    all_rows = journal_forecast._recent_decisions(history)
    assert [item["reasoning"] for item in all_rows] == [f"because {i}" for i in range(4)]
