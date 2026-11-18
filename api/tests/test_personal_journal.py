import json
from copy import deepcopy

import httpx
import pytest
from fastapi.testclient import TestClient

from api.main import app
from preferences import journal_forecast, journal_reasoning, journal_reasoning_v2


PATH = "/api/preferences/journal/forecast"
PAIRED = "/api/preferences/journal/paired"
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


def test_wording_baseline_handles_empty_history_and_changed_or_reversed_choices(client, monkeypatch):
    monkeypatch.setenv("PERSONAL_JOURNAL_MODEL_MODE", "baseline")
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


@pytest.mark.parametrize("mode", ["baseline", "reasoning"])
def test_unrelated_wording_offers_no_evidence(client, monkeypatch, mode):
    monkeypatch.setenv("PERSONAL_JOURNAL_MODEL_MODE", mode)
    req = packet()
    req["history"] = [earlier()]
    req["measure"].update(yesMeaning="Install photovoltaic panels", noMeaning="Continue burning gas")
    assert forecast(client, req)["probabilityYes"] == 0.5


@pytest.mark.parametrize("mode", ["baseline", "reasoning"])
def test_ballot_label_boilerplate_does_not_supply_preference_evidence(client, monkeypatch, mode):
    monkeypatch.setenv("PERSONAL_JOURNAL_MODEL_MODE", mode)
    req = packet()
    prior = earlier()
    prior["measure"].update(yesMeaning="A YES vote would repair bridges", noMeaning="A NO vote would defer maintenance")
    req["history"] = [prior]
    req["measure"].update(yesMeaning="A YES vote would fund daycare", noMeaning="A NO vote would cut subsidies")
    assert forecast(client, req)["probabilityYes"] == 0.5


@pytest.mark.parametrize("path", [PATH, PAIRED])
@pytest.mark.parametrize("level", ["top", "measure", "history"])
def test_current_vote_is_not_an_input_or_reflected_in_errors(client, level, path):
    req = packet()
    req["history"] = [earlier()]
    target = {"top": req, "measure": req["measure"], "history": req["history"][0]}[level]
    target["actualVote"] = "private-invalid-answer"
    response = client.post(path, headers=HEADERS, json=req)
    assert response.status_code == 422
    assert "private-invalid-answer" not in response.text


@pytest.mark.parametrize("path", [PATH, PAIRED])
def test_private_route_requires_launcher_loopback_and_token(client, monkeypatch, path):
    assert client.post(path, json=packet()).status_code == 403
    outside = TestClient(app, client=("192.0.2.123", 7921))
    assert outside.post(path, headers=HEADERS, json=packet()).status_code == 403
    monkeypatch.setenv("NODE_ENV", "production")
    assert client.post(path, headers=HEADERS, content=b"bad-json").status_code == 404
    monkeypatch.delenv("NODE_ENV")
    monkeypatch.delenv("PERSONAL_JOURNAL_LOCAL")
    assert client.post(path, headers=HEADERS, json=packet()).status_code == 404
    monkeypatch.setenv("PERSONAL_JOURNAL_LOCAL", "1")
    monkeypatch.delenv("PERSONAL_JOURNAL_API_TOKEN")
    assert client.post(path, headers=HEADERS, json=packet()).status_code == 404


def pair(client, req):
    response = client.post(PAIRED, headers=HEADERS, json={**req, "modelVersion": "reasoning-examples-v2"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_pair_pins_the_original_models_and_masks_only_written_evidence(client, monkeypatch):
    req = packet()
    req["measure"].update(yesMeaning="Require independent audits", noMeaning="Retain internal review")
    req["history"] = [earlier("no")]
    req["history"][0].update(reasoning="I prefer independent audits.", clarification={
        "kind": "weight", "question": "Which safeguard matters?", "answer": "I value independent audits.",
    })
    masked = deepcopy(req)
    masked["history"][0].update(reasoning="", clarification=None)
    direct_reasoning = forecast(client, req)
    direct_ablation = forecast(client, masked)
    monkeypatch.setenv("PERSONAL_JOURNAL_MODEL_MODE", "baseline")
    direct_baseline = forecast(client, req)
    monkeypatch.setenv("PERSONAL_JOURNAL_MODEL_MODE", "llm")
    monkeypatch.setattr(journal_forecast.httpx, "Client", lambda **options: pytest.fail("Unexpected provider"))
    result = pair(client, req)
    assert result == {
        "baseline": direct_baseline, "reasoning": direct_reasoning,
        "withoutReasoning": {**direct_ablation, "model": "reasoning-examples-v2-without-reasoning"},
    }
    for field in ("reasoning", "clarification"):
        single_note = deepcopy(masked)
        single_note["history"][0][field] = req["history"][0][field]
        singly_informed = pair(client, single_note)
        assert singly_informed["reasoning"]["probabilityYes"] > direct_ablation["probabilityYes"]
        assert singly_informed["withoutReasoning"] == result["withoutReasoning"]
        assert singly_informed["baseline"] == result["baseline"]


@pytest.mark.parametrize("history", [[], [earlier()]])
def test_paired_forecasts_use_one_tie_break_and_reverse_when_labels_flip(client, history):
    req = packet()
    req["history"] = history
    before = pair(client, req)
    if not history:
        assert {arm["probabilityYes"] for arm in before.values()} == {.5}
        assert len({arm["choice"] for arm in before.values()}) == 1
    measure = req["measure"]
    measure["noMeaning"], measure["yesMeaning"] = measure["yesMeaning"], measure["noMeaning"]
    after = pair(client, req)
    for arm, prediction in before.items():
        assert after[arm]["choice"] != prediction["choice"]
        assert after[arm]["probabilityYes"] == pytest.approx(1 - prediction["probabilityYes"])
        assert after[arm]["historyCount"] == len(history)


def test_partial_pair_failure_returns_no_predictions_or_private_details(client, monkeypatch):
    def broken_forecast(req):
        raise ValueError("private input caused a failure")
    monkeypatch.setattr(journal_reasoning_v2, "paired_forecast", broken_forecast)
    response = client.post(PAIRED, headers=HEADERS, json={**packet(), "modelVersion": "reasoning-examples-v2"})
    assert response.status_code == 500
    assert response.json() == {"detail": "The model comparison could not be computed."}


def test_old_frozen_checks_use_the_original_scoring_and_unknown_versions_fail_closed(client):
    req = {**packet(), "history": [earlier("no")]}
    expected = journal_reasoning.paired_forecast(journal_forecast.JournalRequest.model_validate(req)).model_dump()
    for version in ({}, {"modelVersion": "reasoning-examples-v1"}):
        result = client.post(PAIRED, headers=HEADERS, json={**req, **version})
        assert result.status_code == 200 and result.json() == expected
    result = client.post(PAIRED, headers=HEADERS, json={**req, "modelVersion": "unknown"})
    assert result.status_code == 422


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
    req["history"][0]["clarification"] = {"question": "What time matters?", "answer": "Early mornings."}
    def handler(request):
        assert str(request.url) == "http://127.0.0.1:11434/v1/chat/completions"
        messages = json.loads(request.content)["messages"]
        data = json.loads(messages[-1]["content"])
        assert data["earlierDecisions"][0]["reasoning"] == req["history"][0]["reasoning"]
        assert data["earlierDecisions"][0]["clarification"] == req["history"][0]["clarification"]
        assert data["currentMeasure"] == {key: MEASURE[key] for key in ["title", "text", "yesMeaning", "noMeaning"]}
        prediction = json.dumps({"probabilityYes": 0.8, "explanation": "Earlier weekend choices align."})
        return httpx.Response(200, json={"choices": [{"message": {"content": prediction}}]})
    mock_provider(monkeypatch, handler)
    result = forecast(client, req)
    assert result == {"choice": "yes", "probabilityYes": 0.8, "model": "local-llm-v2/fixture-model",
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


ID_A = "77000000-0000-4000-8000-000000000001"
ID_B = "77000000-0000-4000-8000-000000000002"
PROFILE = PATH.replace("/forecast", "/profile")
QUESTION = PATH.replace("/forecast", "/question")


def evidence(identity=ID_A, **updates):
    return {**earlier(), "id": identity, **updates}


def test_default_forecast_learns_stance_and_answer_without_a_topic_map(client):
    req = packet()
    req["measure"].update(yesMeaning="Require independent audits", noMeaning="Retain internal review")
    assert forecast(client, req)["probabilityYes"] == .5
    item = evidence(reasoning="I support independent audits.")
    req["history"] = [item]
    positive = forecast(client, req)
    assert positive["model"] == "reasoning-examples-v2" and positive["probabilityYes"] > .5
    # The ballot and vote are identical. Changing only the reason flips the estimate.
    item["reasoning"] = "I do not support independent audits."
    assert forecast(client, req)["probabilityYes"] < .5
    item["reasoning"] = "I return books each week."
    assert forecast(client, req)["probabilityYes"] == .5
    item["clarification"] = {"question": "What about independent audits?", "answer": "Long hours."}
    assert forecast(client, req)["probabilityYes"] == .5  # question text is never voter evidence
    item["clarification"]["answer"] = "I oppose independent audits."
    original = forecast(client, req)
    assert original["probabilityYes"] < .5
    assert original["historyCount"] == 1
    req["measure"]["yesMeaning"], req["measure"]["noMeaning"] = req["measure"]["noMeaning"], req["measure"]["yesMeaning"]
    assert forecast(client, req)["probabilityYes"] == pytest.approx(1 - original["probabilityYes"])


def test_reasons_can_emphasize_an_outcome_without_an_explicit_stance(client):
    req = packet()
    req["measure"].update(yesMeaning="Saturday", noMeaning="Sunday")
    item = evidence(reasoning="This is a difficult decision.")
    req["history"] = [item]
    unweighted = forecast(client, req)["probabilityYes"]
    item["reasoning"] = "Saturday fits my schedule."
    assert forecast(client, req)["probabilityYes"] > unweighted > .5
    item["vote"] = "no"
    item["reasoning"] = "Saturday costs too much."
    assert forecast(client, req)["probabilityYes"] < .5
    # Conditions outside the available outcomes do not become unconditional preferences.
    req["measure"].update(yesMeaning="Independent audits", noMeaning="Internal review")
    item["reasoning"] = "I support independent audits only if grants are available."
    assert forecast(client, req)["probabilityYes"] == .5


def test_private_profile_links_actual_quoted_reasons_and_clarification(client):
    reason = "I support upgrades only if the building stays open."
    clarified = "I value evening access."
    req = {"history": [evidence(reasoning=reason), evidence(ID_B, reasoning=reason,
           clarification={"question": "Is parking necessary?", "answer": clarified})]}
    response = client.post(PROFILE, headers=HEADERS, json=req)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    profile = response.json()
    assert profile["model"] == "reasoning-examples-v2" and profile["evidenceCount"] == 2
    by_label = {f["label"]: set(f["evidenceIds"]) for f in profile["facets"]}
    assert by_label == {reason: {ID_A, ID_B}, clarified: {ID_B}}
    assert client.post(PROFILE, headers=HEADERS, json={"history": []}).json()["facets"] == []


def test_actual_switch_question_answer_applies_only_to_matching_revised_alternative(client):
    item = evidence(vote="no", reasoning="The purchase is too costly.")
    item["measure"].update(yesMeaning="Purchase a bookmobile", noMeaning="Lease a bookmobile")
    target = {**item, "prediction": {"choice": "yes", "probabilityYes": .5,
              "model": "earlier", "explanation": "Tie.", "historyCount": 0}}
    question = client.post(QUESTION, headers=HEADERS, json={"target": target, "history": []}).json()["question"]
    assert question["kind"] == "counterfactual"
    prompt = question["prompt"]
    assert "Purchase a bookmobile" in prompt
    req = packet()
    req["history"] = [item]
    req["measure"].update(yesMeaning="Purchase a bookmobile with independent audits", noMeaning="Lease a bookmobile")
    original = forecast(client, req)["probabilityYes"]
    assert original < .5
    item["clarification"] = {"question": prompt, "answer": "If there were an independent audit."}
    assert forecast(client, req)["probabilityYes"] == original  # untyped legacy prompt
    item["clarification"].update(kind="counterfactual", question="A reworded question about the other outcome.")
    switched = forecast(client, req)
    assert switched["probabilityYes"] > .5
    assert item["clarification"]["answer"] in switched["explanation"]
    item["clarification"]["answer"] = "If there were a purchase warranty."
    assert forecast(client, req)["probabilityYes"] == original
    item["clarification"]["answer"] = "If there were an independent audit."
    req["measure"].update(yesMeaning="Lease a bookmobile", noMeaning="Purchase a bookmobile with an independent audit")
    assert forecast(client, req)["probabilityYes"] == pytest.approx(1 - switched["probabilityYes"])
    # Same condition, but attached to the option that was chosen previously.
    req["measure"].update(yesMeaning="Purchase a bookmobile", noMeaning="Lease a bookmobile with an independent audit")
    assert forecast(client, req)["probabilityYes"] < .5
    # Both options meet the stated condition: it does not distinguish this ballot.
    req["measure"].update(yesMeaning="Purchase a bookmobile with an independent audit")
    assert forecast(client, req)["probabilityYes"] < .5
    req["measure"].update(yesMeaning="Assign independent audits", noMeaning="Appoint outside supervisors")
    assert forecast(client, req)["probabilityYes"] == .5
    # An explicit removal requires evidence of that removal. Missing language is insufficient.
    item["clarification"]["answer"] = "If the surcharge were removed."
    req["measure"].update(yesMeaning="Purchase a bookmobile", noMeaning="Lease a bookmobile")
    assert forecast(client, req)["probabilityYes"] < .5
    req["measure"].update(yesMeaning="Purchase a bookmobile without a surcharge")
    assert forecast(client, req)["probabilityYes"] > .5
    item["clarification"]["answer"] = "Maybe, if the surcharge were removed, but only sometimes."
    assert forecast(client, req)["probabilityYes"] < .5


def test_equally_relevant_conflicting_reasons_cancel(client):
    req = packet()
    req["measure"].update(yesMeaning="Independent audits", noMeaning="Board hearings")
    req["history"] = [evidence(reasoning="I support independent audits."),
                      evidence(ID_B, reasoning="I oppose independent audits.")]
    assert forecast(client, req)["probabilityYes"] == .5


def test_procedural_agreement_across_seven_unrelated_ballots_is_no_evidence(client):
    def entry(label, i):
        item = evidence(f"77000000-0000-4000-8000-{i:012d}", reasoning=f"I support {label}.")
        item["measure"].update(title=label, text=f"Proposed {label}", yesMeaning=f"Approve {label}",
                               noMeaning=f"Reject {label}")
        return item
    history = [entry(label, i) for i, label in enumerate(
        ("bookmobiles", "parade", "tennis", "arboretum", "ferries", "signage", "shelters"), 1)]
    target = entry("aqueduct", 8)
    req = {**packet(), "history": history, "measure": target["measure"]}
    assert forecast(client, req)["probabilityYes"] == .5
    req["measure"]["yesMeaning"], req["measure"]["noMeaning"] = req["measure"]["noMeaning"], req["measure"]["yesMeaning"]
    cold = forecast(client, req)
    assert cold["probabilityYes"] == .5
    result = client.post(QUESTION, headers=HEADERS, json={"target": {**target, "prediction": cold}, "history": history})
    assert result.status_code == 200 and "referenceId" not in result.json()["question"]


def test_forecast_cites_contributing_notes_and_profile_contrast_considers_answers(client):
    req = packet()
    item = evidence(reasoning="My visiting schedule varies. Saturday fits my working hours.")
    req["history"] = [item]
    req["measure"].update(yesMeaning="Saturday", noMeaning="Sunday")
    result = forecast(client, req)
    assert "Saturday fits my working hours." in result["explanation"]
    item["reasoning"] = "My visiting schedule varies."
    result = forecast(client, req)
    assert item["reasoning"] not in result["explanation"] and "wording" in result["explanation"]
    target = question_packet(choice="no", p=.3)
    unrelated = evidence(ID_B, reasoning="Numbers remain low.")
    unrelated["measure"].update(title="Power storage", text="Batteries save energy.",
                                yesMeaning="Add batteries", noMeaning="Replace generators")
    target["history"] = [unrelated]
    assert "referenceId" not in client.post(QUESTION, headers=HEADERS, json=target).json()["question"]
    unrelated["clarification"] = {"question": "What would matter elsewhere?",
                                  "answer": "The library needs a weekend extension of library hours through Saturday."}
    assert client.post(QUESTION, headers=HEADERS, json=target).json()["question"]["referenceId"] == ID_B


def question_packet(choice="yes", p=.9):
    item = evidence(vote="yes")
    item["prediction"] = {"choice": choice, "probabilityYes": p, "model": "original-frozen",
                          "explanation": "Initial estimate.", "historyCount": 0}
    return {"target": item, "history": []}


@pytest.mark.parametrize(("choice","p","trigger"), [
    ("yes", .9, None), ("yes", .6, "uncertain"), ("yes", .5, "uncertain"),
    ("no", .5, "miss"), ("no", .1, "miss"),
])
def test_followup_policy_uses_locked_forecast_and_ground_truth(client, choice, p, trigger):
    req = question_packet(choice, p)
    response = client.post(QUESTION, headers=HEADERS, json=req)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    result = response.json()["question"]
    if trigger is None:
        assert result is None
    else:
        assert result["trigger"] == trigger and "referenceId" not in result
        assert req["target"]["reasoning"] in result["prompt"]
        if p == .5:
            assert "model give" not in result["prompt"]


def test_contrast_question_uses_related_actual_outcomes_and_excludes_self(client):
    req = question_packet(choice="no", p=.3)
    unrelated = evidence(ID_B, reasoning="The shade is valuable.")
    unrelated["measure"].update(title="Elm planting", text="Plant elms by the river.",
                                yesMeaning="Plant additional elms", noMeaning="Remove diseased elms")
    req["history"] = [unrelated, evidence()]
    assert "referenceId" not in client.post(QUESTION, headers=HEADERS, json=req).json()["question"]
    related = evidence(ID_B, vote="no")
    related["measure"].update(title="North branch weekend opening")
    req["history"] = [related]
    result = client.post(QUESTION, headers=HEADERS, json=req).json()["question"]
    assert result["referenceId"] == ID_B and result["kind"] == "contrast"
    assert related["measure"]["noMeaning"] in result["prompt"] and MEASURE["yesMeaning"] in result["prompt"]


@pytest.mark.parametrize("path", [PROFILE, QUESTION])
def test_private_policy_routes_check_token_before_parsing_and_sanitize_errors(client, path):
    assert client.post(path, content=b"raw private data").status_code == 403
    response = client.post(path, headers=HEADERS, json={"private-marker": "sensitive text"})
    assert response.status_code == 422 and "sensitive text" not in response.text
