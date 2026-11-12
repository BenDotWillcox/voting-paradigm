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
PEOPLE_URL = "/api/delegation/people"
CITY_URL = "/api/delegation/city"

VIEWER = "you"
# Open ballot papers, and two that have closed
GENERAL = "city-general-3"
SPECIAL = "district-2-special-2"
ADVISORY = "city-advisory-2"
CLOSED_GENERAL = "city-general-2"
CLOSED_BUDGET = "city-budget"
OPEN_QUESTIONS = 21
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
        papers = body["ballot_papers"]
        assert len(papers) == 12
        assert sum(len(p["questions"]) for p in papers) == 68
        assert [p["closes_in_days"] for p in papers] == sorted(
            p["closes_in_days"] for p in papers
        )
        assert [
            (p["id"], p["eligible_voters"], len(p["questions"]))
            for p in papers
            if p["status"] == "open"
        ] == [
            (SPECIAL, 80, 3),
            (GENERAL, 241, 14),
            ("district-1-special-3", 81, 2),
            (ADVISORY, 241, 2),
        ]
        assert all((p["status"] == "open") == (p["closes_in_days"] > 0) for p in papers)
        assert len(body["categories"]) == 30
        assert all(category["in_pool"] for category in body["categories"])

    def test_viewer_is_a_resident_whose_account_starts_with_delegations(
        self, client: TestClient
    ) -> None:
        body = client.get(SCENARIO_URL).json()
        viewer = next(p for p in body["persons"] if p["id"] == VIEWER)
        assert (viewer["name"], viewer["username"]) == ("You", "you")
        assert viewer["home"] == "district-1"
        assert viewer["residences"] == ["city", "district-1"]
        assert viewer["behaviour"] is None
        # The simulated network holds none; the account's starting ones are separate.
        assert not [d for d in body["delegations"] if d["delegator"] == VIEWER]
        starting = body["viewer_delegations"]
        assert len(starting) == 8
        assert len({d["category"] for d in starting}) == 8
        people = {p["id"] for p in body["persons"]}
        assert all(d["delegate"] in people for d in starting)

    def test_the_starting_account_passes_the_creation_checks(
        self, client: TestClient
    ) -> None:
        starting = client.get(SCENARIO_URL).json()["viewer_delegations"]
        resolve(client, viewer_delegations=starting)

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

    def test_names_usernames_and_well_known_people(self, client: TestClient) -> None:
        body = client.get(SCENARIO_URL).json()
        by_id = {person["id"]: person for person in body["persons"]}
        usernames = [person["username"] for person in body["persons"]]
        assert len(set(usernames)) == len(usernames)
        assert all(
            " " in person["name"]
            for person in body["persons"]
            if person["id"] != VIEWER
        )
        assert by_id["d2-022"]["home"] == "district-2"
        assert by_id["out-03"]["home"] is None
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
        assert len(result["questions"]) == 14
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
        # The delegate has voted, or is still due to.
        assert receipt["choice"] in (["yes"], ["no"], None)
        assert receipt["scores"][0]["probability"] >= receipt["threshold"]

    def test_a_question_about_nothing_the_viewer_delegated_stays(
        self, client: TestClient
    ) -> None:
        result = resolve(client, viewer_delegations=delegations((TAXES, KEEPER)))
        receipt = question(result, "q39")["receipt"]  # Civilian police review board
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
        assert resolvers["q39"] == VIEWER  # the police review board

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
            viewer_votes={"q01": ["yes"]},
        )
        item = question(result, "q01")
        assert item["receipt"]["outcome"] == "direct_vote"
        assert item["receipt"]["resolver"] == VIEWER
        assert item["receipt"]["choice"] == ["yes"]
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
        flag = question(resolve(client, ADVISORY), "q66")["metrics"]  # New city flag
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
        assert held >= 1

        answered = question(
            resolve(client, SPECIAL, viewer_votes={"q34": ["yes"]}), "q34"
        )
        assert answered["inbox"]["answered"] is True
        # The rest are people who have not voted, or whose resolver has not.
        assert (
            answered["delegated"]["abstentions"]
            == waiting["delegated"]["abstentions"] - held
        )
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
        assert judged["judgments"] == {
            "recorded": 0,
            "fetched": OPEN_QUESTIONS,
            "missing": 0,
        }

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
        assert body["judgments"] == {
            "recorded": OPEN_QUESTIONS,
            "fetched": 0,
            "missing": 0,
        }
        assert body["inside"] == [ENVIRONMENT]
        assert len(body["scores"]) == OPEN_QUESTIONS
        assert all(score["probability"] is not None for score in body["scores"])
        best = max(body["scores"], key=lambda score: score["probability"])
        assert best["question_id"] == "q10"

    def test_without_the_model_a_written_category_stays_unjudged(
        self, client: TestClient
    ) -> None:
        body = client.post(JUDGMENTS_URL, json={"category": WRITTEN}).json()
        assert body["category"]["in_pool"] is False
        assert body["live"] is False
        assert body["judgments"] == {
            "recorded": 0,
            "fetched": 0,
            "missing": OPEN_QUESTIONS,
        }
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
        assert first["judgments"]["fetched"] == OPEN_QUESTIONS
        assert second["judgments"] == {
            "recorded": OPEN_QUESTIONS,
            "fetched": 0,
            "missing": 0,
        }
        assert (
            source.judge_calls == OPEN_QUESTIONS
        )  # one request per open question, once
        assert second["scores"] == first["scores"]

    def test_a_failing_model_is_reported_and_nothing_is_recorded(
        self, client: TestClient, stores: service.RuntimeStores
    ) -> None:
        use_source(ScriptedSource({}, fail=True))
        body = client.post(JUDGMENTS_URL, json={"category": WRITTEN}).json()
        assert body["judgments"]["missing"] == OPEN_QUESTIONS
        assert len(body["failures"]) == OPEN_QUESTIONS
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
            (SPECIAL, "q34"),
            (GENERAL, "q33"),
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
    assert paths == {
        SCENARIO_URL,
        VALIDATE_URL,
        JUDGMENTS_URL,
        RESOLVE_URL,
        PEOPLE_URL + "/{person_id}",
        CITY_URL,
    }
    for path in paths:
        for operation in schema["paths"][path].values():
            assert operation["tags"] == ["delegation"]
            assert operation["summary"] and operation["description"]


class TestClosedPapers:
    def test_a_closed_paper_ignores_the_request(self, client: TestClient) -> None:
        plain = resolve(client, CLOSED_GENERAL)
        changed = resolve(
            client,
            CLOSED_GENERAL,
            viewer_delegations=delegations((TRANSPORT, KEEPER)),
            viewer_votes={"q11": ["yes"]},
            threshold=0.95,
        )
        assert plain == changed
        assert plain["status"] == "closed"
        assert plain["closes_in_days"] < 0
        assert plain["threshold"] == 0.7

    def test_history_uses_the_starting_account(self, client: TestClient) -> None:
        starting = {
            d["category"]: d["delegate"]
            for d in client.get(SCENARIO_URL).json()["viewer_delegations"]
        }
        receipt = question(resolve(client, CLOSED_GENERAL), "q11")["receipt"]
        # Zoo conservation fund for Amazon tree frogs: the narrow category wins.
        assert receipt["outcome"] == "delegated"
        assert receipt["category"] == FROGS
        assert receipt["chain"][:2] == [VIEWER, starting[FROGS]]

    def test_the_viewer_voted_on_some_past_questions_despite_a_delegation(
        self, client: TestClient
    ) -> None:
        receipt = question(resolve(client, CLOSED_BUDGET), "q25")["receipt"]
        assert receipt["outcome"] == "direct_vote"
        assert receipt["choice"] in (["yes"], ["no"])

    def test_an_open_paper_reports_its_deadline(self, client: TestClient) -> None:
        result = resolve(client, SPECIAL)
        assert (result["status"], result["closes_in_days"]) == ("open", 3)


class TestProfile:
    def profile(self, client: TestClient, person: str) -> dict[str, Any]:
        response = client.get(f"{PEOPLE_URL}/{person}")
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    def test_counts_add_up_and_history_is_newest_first(
        self, client: TestClient
    ) -> None:
        body = self.profile(client, "d2-022")
        stats, history = body["stats"], body["history"]
        issued = [entry for entry in history if entry["issued"]]

        assert body["person"]["username"]
        # A District 2 resident is issued the city papers and their district's.
        assert stats["votes_issued"] == len(issued) == 35 + 4
        assert (
            stats["voted_personally"] + stats["delegated"] + stats["abstained"]
            == stats["votes_issued"]
        )
        assert stats["delegation_rate"] == round(
            stats["delegated"] / stats["votes_issued"], 4
        )
        assert [entry["closed_days_ago"] for entry in history] == sorted(
            entry["closed_days_ago"] for entry in history
        )
        assert stats["categories_handed_over"] == len(body["delegations"])

    def test_a_delegated_vote_names_its_category_chain_and_resolver(
        self, client: TestClient
    ) -> None:
        history = self.profile(client, "d2-022")["history"]
        delegated = [entry for entry in history if entry["how"] == "delegated"]
        assert delegated
        for entry in delegated:
            assert entry["category"]
            assert entry["chain"][0] == "d2-022"
            assert entry["chain"][-1] == entry["resolver"] != "d2-022"
        for entry in history:
            if entry["how"] == "voted":
                assert entry["resolver"] == "d2-022" and entry["choice"]

    def test_the_viewers_profile_is_their_starting_account(
        self, client: TestClient
    ) -> None:
        body = self.profile(client, VIEWER)
        starting = client.get(SCENARIO_URL).json()["viewer_delegations"]
        assert body["delegations"] == starting
        assert body["stats"]["delegators"] == len(body["received"]) == 9
        hows = {entry["how"] for entry in body["history"]}
        assert hows == {"voted", "delegated", "abstained"}
        # The viewer also decides for people in districts they do not live in.
        assert any(
            not entry["issued"] and entry["votes_for_others"] > 0
            for entry in body["history"]
        )

    def test_an_outsider_has_no_votes_of_their_own_but_decides_for_others(
        self, client: TestClient
    ) -> None:
        body = self.profile(client, "out-16")
        assert body["person"]["home"] is None
        assert body["stats"]["votes_issued"] == 0
        assert body["stats"]["delegation_rate"] is None
        assert body["stats"]["votes_decided_for_others"] > 0
        assert body["stats"]["largest_share"] > 0
        assert all(not entry["issued"] for entry in body["history"])

    def test_profiles_never_change(self, client: TestClient) -> None:
        assert self.profile(client, "d1-078") == self.profile(client, "d1-078")

    def test_an_unknown_person_is_rejected(self, client: TestClient) -> None:
        assert client.get(f"{PEOPLE_URL}/nobody").status_code == 422


class TestDailyAllowance:
    def test_new_categories_stop_at_the_days_allowance(
        self, client: TestClient, stores: service.RuntimeStores, tmp_path: Path
    ) -> None:
        capped = service.RuntimeStores(
            judgments=stores.judgments,
            nesting=stores.nesting,
            usage=tmp_path / "usage.json",
            daily_cap=1,
        )
        app.dependency_overrides[service.default_stores] = lambda: capped
        source = ScriptedSource({})
        use_source(source)

        first = client.post(JUDGMENTS_URL, json={"category": WRITTEN}).json()
        second = client.post(JUDGMENTS_URL, json={"category": "street murals"}).json()

        assert first["limited"] is False
        assert first["judgments"]["fetched"] == OPEN_QUESTIONS
        assert second["limited"] is True
        assert second["judgments"]["missing"] == OPEN_QUESTIONS
        assert source.judge_calls == OPEN_QUESTIONS

    def test_a_category_already_on_record_does_not_use_the_allowance(
        self, client: TestClient, stores: service.RuntimeStores, tmp_path: Path
    ) -> None:
        capped = service.RuntimeStores(
            judgments=stores.judgments,
            nesting=stores.nesting,
            usage=tmp_path / "usage.json",
            daily_cap=1,
        )
        app.dependency_overrides[service.default_stores] = lambda: capped
        use_source(ScriptedSource({}))

        client.post(JUDGMENTS_URL, json={"category": WRITTEN})
        again = client.post(JUDGMENTS_URL, json={"category": WRITTEN}).json()
        assert again["limited"] is False
        assert again["judgments"]["recorded"] == OPEN_QUESTIONS


class TestMeasures:
    def scenario(self, client: TestClient) -> dict[str, Any]:
        body: dict[str, Any] = client.get(SCENARIO_URL).json()
        return body

    def measures(self, client: TestClient) -> dict[str, dict[str, Any]]:
        return {
            item["id"]: item
            for paper in self.scenario(client)["ballot_papers"]
            for item in paper["questions"]
        }

    def test_the_city_and_its_districts_are_named(self, client: TestClient) -> None:
        body = self.scenario(client)
        names = {item["id"]: item["name"] for item in body["jurisdictions"]}
        assert body["city"] == names["city"] == "Port Alder"
        assert names["district-2"] == "Harbor"

    def test_a_measure_carries_what_the_ballot_paper_prints(
        self, client: TestClient
    ) -> None:
        bond = self.measures(client)["q21"]  # School construction bond
        assert bond["label"].startswith("Measure ") and bond["kind"] == "Bond"
        assert bond["ballot_type"] == "single_choice"
        assert bond["method"] == "plurality"
        assert bond["wording"].startswith("Shall ")
        assert bond["fiscal"] and bond["placed_by"]
        assert bond["argument_for"] and bond["argument_against"]
        assert bond["site"] is None

    def test_some_measures_are_ranked_or_take_approvals(
        self, client: TestClient
    ) -> None:
        measures = self.measures(client)
        flag, library = measures["q66"], measures["q60"]
        assert (flag["ballot_type"], flag["method"]) == ("ranked", "irv")
        assert (library["ballot_type"], library["method"]) == ("approval", "approval")
        assert len(flag["options"]) == 4
        assert all(option["note"] for option in library["options"])
        assert measures["q34"]["site"] == [0.3, 0.3]  # Bike lane on Main Street

    def test_residents_have_a_location_and_outsiders_do_not(
        self, client: TestClient
    ) -> None:
        persons = {p["id"]: p for p in self.scenario(client)["persons"]}
        x, y = persons[VIEWER]["location"]
        assert 0 <= x <= 1 and 0.5 <= y <= 1  # Northside is the north half
        assert persons["out-00"]["location"] is None

    def test_papers_say_when_they_opened(self, client: TestClient) -> None:
        for paper in self.scenario(client)["ballot_papers"]:
            assert paper["opens_in_days"] < paper["closes_in_days"]
            if paper["status"] == "open":
                assert paper["opens_in_days"] <= 0

    def test_the_viewers_past_changes_are_listed_newest_first(
        self, client: TestClient
    ) -> None:
        changes = self.scenario(client)["viewer_changes"]
        days = [change["day"] for change in changes]
        assert days == sorted(days, reverse=True) and days[0] < 0
        moved = [c for c in changes if c["before"] and c["after"]]
        assert {c["category"] for c in moved} == {
            "housing and land use",
            "the environment and conservation",
        }


class TestBallotTypes:
    FLAG = ["leaf", "waves", "lighthouse", "current"]

    def test_a_ranked_vote_is_counted_by_instant_runoff(
        self, client: TestClient
    ) -> None:
        result = resolve(client, ADVISORY, viewer_votes={"q66": self.FLAG})
        item = question(result, "q66")
        assert item["ballot_type"] == "ranked"
        assert item["receipt"]["choice"] == self.FLAG
        tally = item["delegated"]
        assert tally["method"] == "irv" and tally["rounds"]
        assert tally["rounds"][0]["counts"] == tally["counts"]
        assert tally["winners"][0] in self.FLAG
        # The yes/no question on the same paper is still counted by plurality.
        other = question(result, "q68")["delegated"]
        assert other["method"] == "plurality" and other["rounds"] == []

    def test_a_ranking_must_name_every_option(self, client: TestClient) -> None:
        for choice in (self.FLAG[:2], self.FLAG + ["leaf"], ["yes"], []):
            response = client.post(
                RESOLVE_URL,
                json={"ballot_paper": ADVISORY, "viewer_votes": {"q66": choice}},
            )
            assert response.status_code == 422, choice

    def test_an_approval_vote_counts_for_the_votes_the_viewer_holds(
        self, client: TestClient
    ) -> None:
        waiting = question(resolve(client, SPECIAL), "q60")  # the library's site
        held = waiting["inbox"]["votes_for_others"]
        assert held >= 1 and waiting["ballot_type"] == "approval"

        answered = question(
            resolve(client, SPECIAL, viewer_votes={"q60": ["civic", "depot"]}), "q60"
        )
        before, after = waiting["delegated"]["counts"], answered["delegated"]["counts"]
        assert answered["delegated"]["method"] == "approval"
        assert after["civic"] == before["civic"] + held
        assert after["depot"] == before["depot"] + held
        assert after["pier"] == before["pier"]

    def test_a_yes_no_question_takes_exactly_one_option(
        self, client: TestClient
    ) -> None:
        for choice in (["yes", "no"], [], ["maybe"]):
            response = client.post(
                RESOLVE_URL,
                json={"ballot_paper": GENERAL, "viewer_votes": {"q01": choice}},
            )
            assert response.status_code == 422, choice

    def test_closed_ranked_and_approval_questions_have_results(
        self, client: TestClient
    ) -> None:
        station = question(resolve(client, "district-2-special-1"), "q41")
        assert station["delegated"]["method"] == "irv"
        assert station["delegated"]["winners"][0] in {"front", "cannery", "marsh"}
        song = question(resolve(client, "city-advisory-1"), "q67")
        assert song["delegated"]["method"] == "approval"
        # Approvals can add up to more than the ballots cast.
        cast = song["delegated"]["total_ballots"] - song["delegated"]["abstentions"]
        assert sum(song["delegated"]["counts"].values()) > cast


class TestTurnout:
    def test_not_everyone_votes_on_a_closed_question(self, client: TestClient) -> None:
        for item in resolve(client, CLOSED_GENERAL)["questions"]:
            direct = item["direct"]
            turnout = 1 - direct["abstentions"] / direct["total_ballots"]
            assert 0.3 < turnout < 0.9
            assert 0 < item["cast_so_far"] < 261

    def test_an_open_paper_counts_only_the_ballots_cast_so_far(
        self, client: TestClient
    ) -> None:
        late = question(resolve(client, ADVISORY), "q68")  # 16 days left
        soon = question(resolve(client, SPECIAL), "q34")  # 3 days left
        assert late["cast_so_far"] / 261 < soon["cast_so_far"] / 261

    def test_a_delegate_who_has_not_voted_yet_is_reported_with_their_day(
        self, client: TestClient
    ) -> None:
        starting = client.get(SCENARIO_URL).json()["viewer_delegations"]
        waiting = [
            item["receipt"]
            for paper in (GENERAL, "district-1-special-3")
            for item in resolve(client, paper, viewer_delegations=starting)["questions"]
            if item["receipt"]["resolver_votes_in_days"] is not None
        ]
        assert waiting
        for receipt in waiting:
            assert receipt["resolver"] != VIEWER and receipt["choice"] is None
            assert receipt["resolver_votes_in_days"] > 0

    def test_the_viewer_is_never_reported_as_due(self, client: TestClient) -> None:
        for item in resolve(client)["questions"]:
            assert item["receipt"]["resolver_votes_in_days"] is None


class TestDatedHistory:
    def test_a_closed_paper_uses_the_delegate_of_its_day(
        self, client: TestClient
    ) -> None:
        starting = {
            d["category"]: d["delegate"]
            for d in client.get(SCENARIO_URL).json()["viewer_delegations"]
        }
        # The plastic bag ban closed before the viewer moved the environment
        # to their present delegate; the protected tree ordinance closed after.
        early = question(resolve(client, "city-general-1"), "q14")["receipt"]
        late = question(resolve(client, "district-1-special-2"), "q13")["receipt"]
        assert early["category"] == late["category"] == ENVIRONMENT
        assert early["chain"][1] != starting[ENVIRONMENT]
        assert late["chain"][1] == starting[ENVIRONMENT]

    def test_a_category_made_later_did_not_route_earlier_votes(
        self, client: TestClient
    ) -> None:
        # Sales tax rates was handed over after the first general ballot.
        receipt = question(resolve(client, "city-general-1"), "q05")["receipt"]
        assert "sales tax rates" not in {score["text"] for score in receipt["scores"]}
        later = question(resolve(client, CLOSED_BUDGET), "q04")["receipt"]
        assert later["category"] == "sales tax rates"


class TestCity:
    def city(self, client: TestClient) -> dict[str, Any]:
        response = client.get(CITY_URL)
        assert response.status_code == 200, response.text
        body: dict[str, Any] = response.json()
        return body

    def test_every_closed_question_is_listed_newest_paper_first(
        self, client: TestClient
    ) -> None:
        body = self.city(client)
        scenario = client.get(SCENARIO_URL).json()
        closed = [p for p in scenario["ballot_papers"] if p["status"] == "closed"]
        assert [paper["id"] for paper in body["papers"]] == [p["id"] for p in closed]
        assert len(body["questions"]) == sum(len(p["questions"]) for p in closed)
        assert body["totals"]["questions"] == len(body["questions"])
        days = [row["closed_days_ago"] for row in body["questions"]]
        assert days == sorted(days)

    def test_a_row_matches_the_resolved_paper(self, client: TestClient) -> None:
        row = next(
            r for r in self.city(client)["questions"] if r["question_id"] == "q11"
        )
        item = question(resolve(client, CLOSED_GENERAL), "q11")
        tally = item["delegated"]
        assert row["cast_delegated"] == tally["total_ballots"] - tally["abstentions"]
        assert row["cast_direct"] == (
            item["direct"]["total_ballots"] - item["direct"]["abstentions"]
        )
        assert row["winners"] == tally["winners"]
        assert row["winner_changed"] == item["winner_changed"]
        assert row["delegated_share"] == item["metrics"]["delegated_share"]
        assert row["support"] == round(tally["counts"]["yes"] / row["cast_delegated"], 4)

    def test_only_yes_no_questions_have_a_yes_share(self, client: TestClient) -> None:
        for row in self.city(client)["questions"]:
            assert (row["support"] is None) == (row["ballot_type"] != "single_choice")

    def test_totals_and_papers_add_up(self, client: TestClient) -> None:
        body = self.city(client)
        rows, totals = body["questions"], body["totals"]
        assert totals["changed"] == sum(row["winner_changed"] for row in rows)
        assert totals["changed"] == sum(paper["changed"] for paper in body["papers"])
        issued = sum(row["voters"] for row in rows)
        assert totals["turnout_direct"] == round(
            sum(row["cast_direct"] for row in rows) / issued, 4
        )
        assert 0 < totals["turnout_direct"] < 1
        assert totals["largest_share"] == max(row["largest_share"] for row in rows)

    def test_deciders_are_ranked_and_agree_with_their_profiles(
        self, client: TestClient
    ) -> None:
        deciders = self.city(client)["deciders"]
        counts = [entry["votes_decided"] for entry in deciders]
        assert counts == sorted(counts, reverse=True) and counts[-1] > 0
        top = deciders[0]
        stats = client.get(f"{PEOPLE_URL}/{top['person']}").json()["stats"]
        assert stats["votes_decided_for_others"] == top["votes_decided"]
        assert stats["largest_share"] == top["largest_share"]


class TestProfileChanges:
    def changes(self, client: TestClient, person: str) -> list[dict[str, Any]]:
        body: dict[str, Any] = client.get(f"{PEOPLE_URL}/{person}").json()
        found: list[dict[str, Any]] = body["changes"]
        return found

    def test_the_viewers_changes_include_their_own_and_those_made_to_them(
        self, client: TestClient
    ) -> None:
        changes = self.changes(client, VIEWER)
        days = [change["day"] for change in changes]
        assert days == sorted(days, reverse=True) and days[0] < 0
        own = [change for change in changes if change["delegator"] == VIEWER]
        scenario = client.get(SCENARIO_URL).json()
        assert len(own) == len(scenario["viewer_changes"])
        for change in changes:
            assert VIEWER in (change["delegator"], change["before"], change["after"])

    def test_a_delegate_sees_who_came_and_went(self, client: TestClient) -> None:
        # The viewer moved housing away from this person and the environment
        # to them on different days.
        moved_from = [
            change
            for change in self.changes(client, "d2-007")
            if change["delegator"] == VIEWER and change["before"] == "d2-007"
        ]
        assert [change["category"] for change in moved_from] == ["housing and land use"]
