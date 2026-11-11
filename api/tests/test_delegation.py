"""
HTTP-layer tests for the liquid democracy routes.

Every test runs with the live decision model switched off and with judgments
for viewer-written categories recorded to a temporary folder, so nothing
here touches the network, needs an API key, or writes into the repo's cache.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, get_args

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.schemas.delegation import KeptLiteral, OutcomeLiteral
from api.services import delegation as service
from delegation import (
    Category,
    CategoryId,
    JudgmentStore,
    JudgmentUnavailable,
    KeepReason,
    NestingStore,
    Question,
    RouteOutcome,
    SourceAnswer,
    create_category,
)

SCENARIO_URL = "/api/delegation/scenario"
VALIDATE_URL = "/api/delegation/delegations/validate"
JUDGMENTS_URL = "/api/delegation/judgments"
RESOLVE_URL = "/api/delegation/resolve"

VIEWER = "you"
GENERAL = "city-general"
SPECIAL = "district-2-special"
# People in the seeded scenario population (see delegation.scenario).
KEEPER = "d1-003"  # keeps every decision
OTHER_KEEPER = "d1-006"
HANDS_TRANSPORT_TO_VIEWER = "d2-022"  # a District 2 resident
TAXES = "all things taxes"
ENVIRONMENT = "the environment and conservation"
FROGS = "the well-being of tree frogs in the Amazon"
TRANSPORT = "transportation and roads"
BIKE_LANES = "bike lanes and cycling safety"
WRITTEN = "protecting urban wildlife"


class ScriptedSource:
    """Stands in for hosted Jev: answers from tables and counts its calls."""

    model = "jev-1.14.0"

    def __init__(
        self,
        questions: Mapping[str, float],
        default: float = 0.05,
        inside: Mapping[tuple[str, str], float] | None = None,
        fail: bool = False,
    ) -> None:
        self.questions = questions
        self.default = default
        self.inside = dict(inside or {})
        self.fail = fail
        self.judge_calls = 0
        self.nesting_calls = 0

    def judge(
        self, question: Question, categories: Sequence[Category]
    ) -> Mapping[CategoryId, SourceAnswer]:
        self.judge_calls += 1
        if self.fail:
            raise JudgmentUnavailable("HTTP 529")
        score = self.questions.get(question.id, self.default)
        return {category.id: SourceAnswer(score, self.model) for category in categories}

    def judge_nesting(
        self, pairs: Sequence[tuple[Category, Category]]
    ) -> Mapping[tuple[CategoryId, CategoryId], SourceAnswer]:
        self.nesting_calls += 1
        return {
            (narrow.id, broad.id): SourceAnswer(
                self.inside.get((narrow.text, broad.text), 0.05), self.model
            )
            for narrow, broad in pairs
        }


@pytest.fixture()
def stores(tmp_path: Path) -> service.RuntimeStores:
    return service.RuntimeStores(
        judgments=JudgmentStore(tmp_path / "judgments.jsonl"),
        nesting=NestingStore(tmp_path / "nesting.jsonl"),
    )


@pytest.fixture()
def client(stores: service.RuntimeStores) -> Iterator[TestClient]:
    app.dependency_overrides[service.default_stores] = lambda: stores
    app.dependency_overrides[service.default_source] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def use_source(source: ScriptedSource | None) -> None:
    app.dependency_overrides[service.default_source] = lambda: source


def delegations(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [
        {"category": category, "delegate": delegate} for category, delegate in pairs
    ]


def resolve(client: TestClient, paper: str = GENERAL, **body: Any) -> dict[str, Any]:
    response = client.post(RESOLVE_URL, json={"ballot_paper": paper, **body})
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


def question(result: dict[str, Any], question_id: str) -> dict[str, Any]:
    found: dict[str, Any] = next(
        q for q in result["questions"] if q["question_id"] == question_id
    )
    return found


class TestScenario:
    def test_network_papers_and_pool(self, client: TestClient) -> None:
        body = client.get(SCENARIO_URL).json()

        assert body["viewer"] == VIEWER
        assert body["model"] == "jev-1.14.0"
        assert body["threshold"] == 0.7
        assert len(body["persons"]) == 261
        assert [j["id"] for j in body["jurisdictions"]] == [
            "city",
            "district-1",
            "district-2",
            "district-3",
        ]
        assert [
            (p["id"], p["eligible_voters"], len(p["questions"]))
            for p in body["ballot_papers"]
        ] == [
            (GENERAL, 241, 15),
            (SPECIAL, 80, 5),
        ]
        assert len(body["categories"]) == 30
        assert all(category["in_pool"] for category in body["categories"])

    def test_viewer_is_a_resident_with_no_delegations(self, client: TestClient) -> None:
        body = client.get(SCENARIO_URL).json()
        viewer = next(p for p in body["persons"] if p["id"] == VIEWER)
        assert viewer["label"] == "You"
        assert viewer["residences"] == ["city", "district-1"]
        assert viewer["behaviour"] is None
        assert not [d for d in body["delegations"] if d["delegator"] == VIEWER]

    def test_people_in_every_district_delegate_to_the_viewer(
        self, client: TestClient
    ) -> None:
        body = client.get(SCENARIO_URL).json()
        delegators = {
            d["delegator"][:2] for d in body["delegations"] if d["delegate"] == VIEWER
        }
        assert delegators == {"d1", "d2", "d3"}

    def test_nesting_is_reported_on_the_narrow_category(
        self, client: TestClient
    ) -> None:
        body = client.get(SCENARIO_URL).json()
        by_text = {category["text"]: category for category in body["categories"]}
        assert by_text[FROGS]["inside"] == [by_text[ENVIRONMENT]["id"]]
        assert by_text[ENVIRONMENT]["inside"] == []

    def test_labels_and_well_known_people(self, client: TestClient) -> None:
        body = client.get(SCENARIO_URL).json()
        by_id = {person["id"]: person for person in body["persons"]}
        assert by_id["d2-022"]["label"] == "District 2 resident 22"
        assert by_id["out-03"]["label"] == "Outside resident 3"
        assert by_id["out-03"]["residences"] == []
        assert sum(bool(person["well_known_for"]) for person in body["persons"]) == 8

    def test_scenario_is_reproducible_and_reports_live_judgments(
        self, client: TestClient
    ) -> None:
        first = client.get(SCENARIO_URL).json()
        assert first == client.get(SCENARIO_URL).json()
        assert first["live_judgments"] is False
        use_source(ScriptedSource({}))
        assert client.get(SCENARIO_URL).json()["live_judgments"] is True


class TestResolve:
    def test_every_resident_gets_one_ballot_per_question(
        self, client: TestClient
    ) -> None:
        result = resolve(client)

        assert result["viewer_eligible"] is True
        assert result["jurisdiction"] == "city"
        assert len(result["questions"]) == 15
        for item in result["questions"]:
            assert item["delegated"]["total_ballots"] == 241
            assert item["direct"]["total_ballots"] == 241
            assert item["metrics"]["voters"] == 241
            assert sum(c["votes"] for c in item["metrics"]["chain_lengths"]) == 241
            assert item["winner_changed"] == (
                set(item["delegated"]["winners"]) != set(item["direct"]["winners"])
            )

    def test_same_request_same_response(self, client: TestClient) -> None:
        body = {"viewer_delegations": delegations((TAXES, KEEPER))}
        assert resolve(client, GENERAL, **body) == resolve(client, GENERAL, **body)

    def test_without_delegations_the_viewer_keeps_every_question(
        self, client: TestClient
    ) -> None:
        receipt = question(resolve(client), "q01")["receipt"]
        assert receipt["outcome"] == "no_delegations"
        assert receipt["chain"] == [VIEWER]
        assert receipt["resolver"] == VIEWER
        assert receipt["choice"] is None  # the viewer has not voted

    def test_a_matching_question_goes_to_the_delegate(self, client: TestClient) -> None:
        result = resolve(client, viewer_delegations=delegations((TAXES, KEEPER)))
        receipt = question(result, "q01")["receipt"]  # Senior property tax freeze

        assert receipt["outcome"] == "delegated"
        assert receipt["category"] == TAXES
        assert receipt["chain"] == [VIEWER, KEEPER]
        assert receipt["resolver"] == KEEPER
        assert receipt["kept_because"] == "no_delegations"
        assert receipt["choice"] in {"yes", "no"}
        assert receipt["scores"][0]["probability"] >= receipt["threshold"]

    def test_a_question_about_nothing_the_viewer_delegated_stays(
        self, client: TestClient
    ) -> None:
        result = resolve(client, viewer_delegations=delegations((TAXES, KEEPER)))
        receipt = question(result, "q66")["receipt"]  # New city flag
        assert receipt["outcome"] == "none_available"
        assert receipt["resolver"] == VIEWER

    def test_one_ballot_fans_out_to_different_resolvers(
        self, client: TestClient
    ) -> None:
        result = resolve(
            client,
            viewer_delegations=delegations(
                (TAXES, KEEPER), (ENVIRONMENT, OTHER_KEEPER)
            ),
        )
        resolvers = {
            item["question_id"]: item["receipt"]["resolver"]
            for item in result["questions"]
        }
        assert resolvers["q01"] == KEEPER  # a tax question
        assert resolvers["q12"] == OTHER_KEEPER  # street tree planting
        assert resolvers["q66"] == VIEWER  # the city flag

    def test_a_narrower_category_overrules_the_broader_one(
        self, client: TestClient
    ) -> None:
        # The broad category is listed first and scores higher on this question.
        result = resolve(
            client,
            viewer_delegations=delegations(
                (ENVIRONMENT, KEEPER), (FROGS, OTHER_KEEPER)
            ),
        )
        receipt = question(result, "q10")["receipt"]  # Amazon amphibian habitat grant
        scores = {score["text"]: score["probability"] for score in receipt["scores"]}

        assert scores[ENVIRONMENT] > scores[FROGS] >= receipt["threshold"]
        assert receipt["category"] == FROGS
        assert receipt["set_aside"] == [ENVIRONMENT]
        assert receipt["resolver"] == OTHER_KEEPER

    def test_the_viewers_own_vote_overrides_their_delegation(
        self, client: TestClient
    ) -> None:
        result = resolve(
            client,
            viewer_delegations=delegations((TAXES, KEEPER)),
            viewer_votes={"q01": "yes"},
        )
        item = question(result, "q01")
        assert item["receipt"]["outcome"] == "direct_vote"
        assert item["receipt"]["resolver"] == VIEWER
        assert item["receipt"]["choice"] == "yes"
        assert item["inbox"]["answered"] is True

    def test_raising_the_threshold_to_one_stops_all_delegation(
        self, client: TestClient
    ) -> None:
        result = resolve(client, threshold=1.0)
        for item in result["questions"]:
            assert item["metrics"]["delegated_share"] == 0
            assert item["delegated"] == item["direct"]
            assert item["winner_changed"] is False

    def test_delegation_concentrates_votes_at_the_default_threshold(
        self, client: TestClient
    ) -> None:
        result = resolve(client)
        shares = [item["metrics"]["largest_share"] for item in result["questions"]]
        assert max(shares) > 0.1
        flag = question(result, "q66")["metrics"]
        assert flag["delegated_share"] == 0 and flag["gini"] == 0


class TestAnsweringForOthers:
    def test_the_viewer_is_not_issued_another_districts_ballot(
        self, client: TestClient
    ) -> None:
        result = resolve(client, SPECIAL)
        assert result["viewer_eligible"] is False
        assert result["jurisdiction"] == "district-2"
        for item in result["questions"]:
            assert item["receipt"] is None
            assert item["delegated"]["total_ballots"] == 80

    def test_but_answers_for_a_resident_who_delegated_to_them(
        self, client: TestClient
    ) -> None:
        item = question(resolve(client, SPECIAL), "q34")  # Bike lane on Main Street
        held = item["inbox"]["held"]
        assert {"voter": HANDS_TRANSPORT_TO_VIEWER, "home": "district-2"} in held
        assert item["inbox"]["votes_for_others"] == len(held) >= 1
        assert item["inbox"]["answered"] is False

    def test_held_votes_are_abstentions_until_the_viewer_votes(
        self, client: TestClient
    ) -> None:
        waiting = question(resolve(client, SPECIAL), "q34")
        held = waiting["inbox"]["votes_for_others"]
        assert waiting["delegated"]["abstentions"] == held

        answered = question(
            resolve(client, SPECIAL, viewer_votes={"q34": "yes"}), "q34"
        )
        assert answered["inbox"]["answered"] is True
        assert answered["delegated"]["abstentions"] == 0
        assert (
            answered["delegated"]["counts"]["yes"]
            == waiting["delegated"]["counts"]["yes"] + held
        )
        assert (
            answered["delegated"]["counts"]["no"]
            == waiting["delegated"]["counts"]["no"]
        )

    def test_passing_a_held_vote_on_takes_it_out_of_the_inbox(
        self, client: TestClient
    ) -> None:
        result = resolve(
            client, SPECIAL, viewer_delegations=delegations((TRANSPORT, KEEPER))
        )
        item = question(result, "q34")
        assert item["inbox"]["votes_for_others"] == 0
        assert item["metrics"]["voters"] == 80


class TestWrittenCategories:
    def test_a_category_with_no_judgments_fails_closed(
        self, client: TestClient
    ) -> None:
        result = resolve(
            client,
            viewer_delegations=delegations((TAXES, KEEPER), (WRITTEN, OTHER_KEEPER)),
        )
        assert result["unjudged_categories"] == [WRITTEN]
        for item in result["questions"]:
            # Even the tax question stays: the rule does not route on partial scores.
            assert item["receipt"]["outcome"] == "router_unavailable"
            assert item["receipt"]["resolver"] == VIEWER

    def test_once_judged_a_written_category_routes(self, client: TestClient) -> None:
        use_source(ScriptedSource({"q12": 0.95}))  # Street tree planting bond
        judged = client.post(JUDGMENTS_URL, json={"category": WRITTEN}).json()
        assert judged["judgments"] == {"recorded": 0, "fetched": 20, "missing": 0}

        use_source(None)  # resolution reads what was recorded
        result = resolve(client, viewer_delegations=delegations((WRITTEN, KEEPER)))
        assert result["unjudged_categories"] == []
        assert question(result, "q12")["receipt"]["resolver"] == KEEPER
        assert question(result, "q01")["receipt"]["outcome"] == "none_available"

    def test_detected_nesting_applies_to_a_written_category(
        self, client: TestClient
    ) -> None:
        # The written category scores below the environment on q12 but sits inside it.
        use_source(ScriptedSource({"q12": 0.75}, inside={(WRITTEN, ENVIRONMENT): 0.9}))
        judged = client.post(
            JUDGMENTS_URL, json={"category": WRITTEN, "held": [ENVIRONMENT]}
        ).json()
        assert judged["inside"] == [ENVIRONMENT]
        assert judged["contains"] == []
        assert judged["nesting"]["fetched"] == 2

        result = resolve(
            client,
            viewer_delegations=delegations(
                (ENVIRONMENT, KEEPER), (WRITTEN, OTHER_KEEPER)
            ),
        )
        receipt = question(result, "q12")["receipt"]
        assert receipt["category"] == WRITTEN
        assert receipt["set_aside"] == [ENVIRONMENT]
        assert receipt["resolver"] == OTHER_KEEPER


class TestJudgments:
    def test_a_pool_category_is_already_on_record(self, client: TestClient) -> None:
        body = client.post(
            JUDGMENTS_URL, json={"category": FROGS, "held": [ENVIRONMENT]}
        ).json()

        assert body["category"]["in_pool"] is True
        assert body["live"] is False
        assert body["judgments"] == {"recorded": 20, "fetched": 0, "missing": 0}
        assert body["inside"] == [ENVIRONMENT]
        assert len(body["scores"]) == 20
        assert all(score["probability"] is not None for score in body["scores"])
        best = max(body["scores"], key=lambda score: score["probability"])
        assert best["question_id"] == "q10"

    def test_without_the_model_a_written_category_stays_unjudged(
        self, client: TestClient
    ) -> None:
        body = client.post(JUDGMENTS_URL, json={"category": WRITTEN}).json()
        assert body["category"]["in_pool"] is False
        assert body["live"] is False
        assert body["judgments"] == {"recorded": 0, "fetched": 0, "missing": 20}
        assert all(score["probability"] is None for score in body["scores"])

    def test_answers_are_recorded_and_never_asked_twice(
        self, client: TestClient
    ) -> None:
        source = ScriptedSource({"q12": 0.9})
        use_source(source)
        first = client.post(JUDGMENTS_URL, json={"category": WRITTEN}).json()
        second = client.post(
            JUDGMENTS_URL, json={"category": "Protecting  URBAN wildlife"}
        ).json()

        assert first["live"] is True
        assert first["judgments"]["fetched"] == 20
        assert second["judgments"] == {"recorded": 20, "fetched": 0, "missing": 0}
        assert source.judge_calls == 20  # one request per curated question, once
        assert second["scores"] == first["scores"]

    def test_a_failing_model_is_reported_and_nothing_is_recorded(
        self, client: TestClient, stores: service.RuntimeStores
    ) -> None:
        use_source(ScriptedSource({}, fail=True))
        body = client.post(JUDGMENTS_URL, json={"category": WRITTEN}).json()
        assert body["judgments"]["missing"] == 20
        assert len(body["failures"]) == 20
        assert len(stores.judgments) == 0

    def test_pool_pairs_are_not_asked_about_nesting(self, client: TestClient) -> None:
        source = ScriptedSource({})
        use_source(source)
        client.post(
            JUDGMENTS_URL, json={"category": FROGS, "held": [ENVIRONMENT, TAXES]}
        )
        assert source.nesting_calls == 0 and source.judge_calls == 0

    @pytest.mark.parametrize("category", ["", "   ", "x" * 201])
    def test_invalid_category_text_is_rejected(
        self, client: TestClient, category: str
    ) -> None:
        assert (
            client.post(JUDGMENTS_URL, json={"category": category}).status_code == 422
        )


class TestValidate:
    def test_a_sound_delegation_is_accepted(self, client: TestClient) -> None:
        body = client.post(
            VALIDATE_URL, json={"proposed": {"category": TAXES, "delegate": KEEPER}}
        ).json()
        assert body["accepted"] is True
        assert body["reason"] is None and body["chain"] is None
        assert body["judged"] is True
        assert body["warnings"] == []
        assert body["category"]["id"] == create_category(TAXES).id

    def test_handing_a_category_back_to_whoever_gave_it_is_rejected(
        self, client: TestClient
    ) -> None:
        body = client.post(
            VALIDATE_URL,
            json={
                "proposed": {
                    "category": TRANSPORT,
                    "delegate": HANDS_TRANSPORT_TO_VIEWER,
                }
            },
        ).json()
        assert body["accepted"] is False
        assert body["chain"] == [VIEWER, HANDS_TRANSPORT_TO_VIEWER, VIEWER]
        assert "loop" in body["reason"]

    def test_a_loop_that_depends_on_the_question_is_a_warning(
        self, client: TestClient
    ) -> None:
        # The delegate hands transportation to the viewer. Bike lane questions
        # match both categories, so on those the vote would come straight back.
        proposed = {"category": BIKE_LANES, "delegate": HANDS_TRANSPORT_TO_VIEWER}
        body = client.post(VALIDATE_URL, json={"proposed": proposed}).json()

        assert body["accepted"] is True
        assert [(w["ballot_paper"], w["question_id"]) for w in body["warnings"]] == [
            (GENERAL, "q33"),
            (SPECIAL, "q34"),
        ]

    def test_on_a_warned_question_everyone_on_the_loop_keeps_it(
        self, client: TestClient
    ) -> None:
        result = resolve(
            client,
            viewer_delegations=delegations((BIKE_LANES, HANDS_TRANSPORT_TO_VIEWER)),
        )
        item = question(result, "q33")  # Protected bike lane network
        assert [VIEWER, HANDS_TRANSPORT_TO_VIEWER] in [
            sorted(loop, reverse=True) for loop in item["metrics"]["loops"]
        ]
        assert item["receipt"]["kept_because"] == "loop"
        assert item["receipt"]["resolver"] == VIEWER
        assert item["receipt"]["chain"] == [VIEWER]
        # A question that matches only one of the two categories does not loop.
        assert question(result, "q01")["metrics"]["loops"] == []

    def test_an_unknown_delegate_is_a_rejection_not_an_error(
        self, client: TestClient
    ) -> None:
        response = client.post(
            VALIDATE_URL, json={"proposed": {"category": TAXES, "delegate": "nobody"}}
        )
        assert response.status_code == 200
        assert response.json()["accepted"] is False
        assert "nobody" in response.json()["reason"]

    def test_delegating_a_category_twice_is_rejected(self, client: TestClient) -> None:
        body = client.post(
            VALIDATE_URL,
            json={
                "viewer_delegations": delegations((TAXES, KEEPER)),
                "proposed": {"category": "All things  TAXES", "delegate": OTHER_KEEPER},
            },
        ).json()
        assert body["accepted"] is False
        assert "already" in body["reason"]

    def test_a_written_category_is_accepted_but_reported_unjudged(
        self, client: TestClient
    ) -> None:
        body = client.post(
            VALIDATE_URL, json={"proposed": {"category": WRITTEN, "delegate": KEEPER}}
        ).json()
        assert body["accepted"] is True
        assert body["judged"] is False
        assert body["category"]["in_pool"] is False


class TestInvalidRequests:
    @pytest.mark.parametrize(
        "body",
        [
            {"ballot_paper": "no-such-paper"},
            {
                "ballot_paper": GENERAL,
                "viewer_delegations": delegations((TAXES, "nobody")),
            },
            {
                "ballot_paper": GENERAL,
                "viewer_delegations": delegations((TAXES, VIEWER)),
            },
            {
                "ballot_paper": GENERAL,
                "viewer_delegations": delegations(
                    (TAXES, KEEPER), (TAXES, OTHER_KEEPER)
                ),
            },
            {
                "ballot_paper": GENERAL,
                "viewer_delegations": delegations(
                    (TRANSPORT, HANDS_TRANSPORT_TO_VIEWER)
                ),
            },
            {
                "ballot_paper": GENERAL,
                "viewer_votes": {"q34": "yes"},
            },  # not on this paper
            {"ballot_paper": GENERAL, "viewer_votes": {"q01": "maybe"}},
            {"ballot_paper": GENERAL, "threshold": 1.5},
            {
                "ballot_paper": GENERAL,
                "viewer_delegations": delegations(("x" * 201, KEEPER)),
            },
            {
                "ballot_paper": GENERAL,
                "viewer_delegations": delegations(
                    *[(f"topic {n}", KEEPER) for n in range(13)]
                ),
            },
        ],
    )
    def test_resolve_rejects(self, client: TestClient, body: dict[str, Any]) -> None:
        response = client.post(RESOLVE_URL, json=body)
        assert response.status_code == 422
        assert "detail" in response.json()

    def test_validate_rejects_an_invalid_existing_state(
        self, client: TestClient
    ) -> None:
        response = client.post(
            VALIDATE_URL,
            json={
                "viewer_delegations": delegations((TAXES, "nobody")),
                "proposed": {"category": ENVIRONMENT, "delegate": KEEPER},
            },
        )
        assert response.status_code == 422


class TestLiveSwitch:
    """The default dependency asks the model only when told to, twice over."""

    def configure(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, text: str
    ) -> None:
        env_file = tmp_path / ".env.local"
        env_file.write_text(text, encoding="utf-8")
        monkeypatch.setattr(service, "ENV_FILE", env_file)
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        monkeypatch.delenv(service.LIVE_VARIABLE, raising=False)
        service.default_source.cache_clear()

    def teardown_method(self) -> None:
        service.default_source.cache_clear()

    def test_a_key_alone_does_not_switch_live_judgments_on(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        self.configure(
            monkeypatch, tmp_path, "TYPESAFE_API_KEY=sk-test-not-a-real-key\n"
        )
        assert service.default_source() is None

    def test_the_switch_alone_is_not_enough(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        self.configure(monkeypatch, tmp_path, f"{service.LIVE_VARIABLE}=1\n")
        assert service.default_source() is None

    def test_key_and_switch_together_give_a_pinned_source(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        self.configure(
            monkeypatch,
            tmp_path,
            f"TYPESAFE_API_KEY=sk-test-not-a-real-key\n{service.LIVE_VARIABLE}=true\n",
        )
        source = service.default_source()
        assert source is not None
        assert source.model == "jev-1.14.0"
        assert "sk-test" not in repr(source)


def test_schema_literals_match_the_domain() -> None:
    assert set(get_args(OutcomeLiteral)) == {outcome.value for outcome in RouteOutcome}
    assert set(get_args(KeptLiteral)) == {reason.value for reason in KeepReason}


def test_routes_are_documented() -> None:
    schema = TestClient(app).get("/openapi.json").json()
    paths = {path for path in schema["paths"] if path.startswith("/api/delegation")}
    assert paths == {SCENARIO_URL, VALIDATE_URL, JUDGMENTS_URL, RESOLVE_URL}
    for path in paths:
        for operation in schema["paths"][path].values():
            assert operation["tags"] == ["delegation"]
            assert operation["summary"] and operation["description"]
