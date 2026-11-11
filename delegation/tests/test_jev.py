"""
Tests for the Jev adapter.

Every request goes to an in-process mock transport. Nothing here touches
the network or needs an API key.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from delegation import Question, create_category
from delegation.jev import (
    API_KEY_VARIABLE,
    JEV_ENDPOINT,
    JEV_MODEL,
    JevSource,
    read_api_key,
)
from delegation.judgments import JudgmentUnavailable
from voting import Candidate

SECRET = "sk-test-not-a-real-key"
YES_NO = (Candidate("yes", "Yes"), Candidate("no", "No"))
LEVY = Question("levy", "Property tax levy", "Adds a levy for schools.", YES_NO)
TAXES = create_category("all things taxes")
SCHOOLS = create_category("public schools")

Handler = Callable[[httpx.Request], httpx.Response]


def source_for(handler: Handler, **options: Any) -> tuple[JevSource, list[float]]:
    """A source wired to a mock transport, with its sleeps captured."""
    waits: list[float] = []
    source = JevSource(
        SECRET,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=waits.append,
        **options,
    )
    return source, waits


def answers(**by_name: Any) -> dict[str, Any]:
    return {
        "model": JEV_MODEL,
        "answers": by_name,
        "usage": {"input_tokens": 120, "output_tokens": 12},
    }


def noul(probability: Any) -> dict[str, Any]:
    return {"type": "noul", "noul": probability}


def good_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, json=answers(**{TAXES.id: noul(0.97), SCHOOLS.id: noul(0.6)})
    )


class TestRequest:
    def test_one_yes_no_question_per_category_about_the_question(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return good_response(request)

        source, _ = source_for(handler)
        source.judge(LEVY, [TAXES, SCHOOLS])

        request = seen[0]
        assert request.method == "POST"
        assert str(request.url) == JEV_ENDPOINT
        assert request.headers["authorization"] == f"Bearer {SECRET}"
        body = json.loads(request.content)
        assert body["model"] == JEV_MODEL
        assert body["state"] == {
            "title": "Property tax levy",
            "summary": "Adds a levy for schools.",
            "options": ["Yes", "No"],
        }
        assert set(body["questions"]) == {TAXES.id, SCHOOLS.id}
        asked = body["questions"][TAXES.id]
        assert asked["type"] == "noul"
        assert asked["instructions"].endswith("Topic: all things taxes")

    def test_only_question_and_category_text_are_sent(self) -> None:
        bodies: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            bodies.append(request.content.decode())
            return good_response(request)

        source, _ = source_for(handler)
        source.judge(LEVY, [TAXES, SCHOOLS])
        assert SECRET not in bodies[0]
        assert set(json.loads(bodies[0])) == {"model", "state", "questions"}

    def test_no_categories_means_no_request(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be sent")

        source, _ = source_for(handler)
        assert source.judge(LEVY, []) == {}
        assert source.requests == 0


class TestAnswers:
    def test_probabilities_come_back_per_category(self) -> None:
        source, _ = source_for(good_response)
        judged = source.judge(LEVY, [TAXES, SCHOOLS])

        assert judged[TAXES.id].probability == 0.97
        assert judged[SCHOOLS.id].probability == 0.6
        assert judged[TAXES.id].answered_by == JEV_MODEL
        assert (source.requests, source.input_tokens) == (1, 120)

    def test_an_answer_from_another_model_is_refused(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            body = answers(**{TAXES.id: noul(0.9)})
            body["model"] = "jev-1.15.0"
            return httpx.Response(200, json=body)

        source, _ = source_for(handler)
        with pytest.raises(JudgmentUnavailable, match="pinned"):
            source.judge(LEVY, [TAXES])

    @pytest.mark.parametrize(
        "answer",
        [
            None,
            {"type": "choice", "choice": "x"},
            noul("0.9"),
            noul(True),
            noul(1.2),
            noul(-0.1),
            noul(None),
        ],
    )
    def test_a_malformed_answer_is_refused(self, answer: Any) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=answers(**{TAXES.id: answer}))

        source, _ = source_for(handler)
        with pytest.raises(JudgmentUnavailable):
            source.judge(LEVY, [TAXES])

    def test_a_missing_answer_is_refused(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=answers(**{TAXES.id: noul(0.9)}))

        source, _ = source_for(handler)
        with pytest.raises(JudgmentUnavailable):
            source.judge(LEVY, [TAXES, SCHOOLS])

    @pytest.mark.parametrize("body", ["not json", "[]", '{"model": "jev-1.14.0"}'])
    def test_an_unreadable_body_is_refused(self, body: str) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=body.encode())

        source, _ = source_for(handler)
        with pytest.raises(JudgmentUnavailable):
            source.judge(LEVY, [TAXES])


class TestFailures:
    def test_transient_statuses_are_retried_then_succeed(self) -> None:
        statuses = iter([529, 429])

        def handler(request: httpx.Request) -> httpx.Response:
            status = next(statuses, None)
            if status is not None:
                return httpx.Response(status, json={"detail": "busy"})
            return good_response(request)

        source, waits = source_for(handler)
        judged = source.judge(LEVY, [TAXES, SCHOOLS])

        assert judged[TAXES.id].probability == 0.97
        assert source.requests == 3
        assert waits == [1.0, 2.0]

    def test_retry_after_is_followed(self) -> None:
        first = iter([True])

        def handler(request: httpx.Request) -> httpx.Response:
            if next(first, False):
                return httpx.Response(429, headers={"retry-after": "7"})
            return good_response(request)

        source, waits = source_for(handler)
        source.judge(LEVY, [TAXES, SCHOOLS])
        assert waits == [7.0]

    def test_attempts_are_bounded(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(529)

        source, waits = source_for(handler, attempts=3)
        with pytest.raises(JudgmentUnavailable, match="3 attempts: HTTP 529"):
            source.judge(LEVY, [TAXES])
        assert source.requests == 3
        assert len(waits) == 2  # no wait after the last attempt

    def test_a_network_error_is_retried_then_reported(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        source, _ = source_for(handler, attempts=2)
        with pytest.raises(JudgmentUnavailable, match="ConnectError"):
            source.judge(LEVY, [TAXES])
        assert source.requests == 2

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 413, 422])
    def test_other_statuses_are_not_retried(self, status: int) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, json={"detail": f"private detail {SECRET}"})

        source, waits = source_for(handler)
        with pytest.raises(JudgmentUnavailable) as failure:
            source.judge(LEVY, [TAXES])

        assert source.requests == 1 and waits == []
        assert str(failure.value) == f"Jev returned HTTP {status}"

    def test_errors_never_carry_the_key_or_the_response_body(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"detail": f"bad key {SECRET}"})

        source, _ = source_for(handler)
        with pytest.raises(JudgmentUnavailable) as failure:
            source.judge(LEVY, [TAXES])
        assert SECRET not in str(failure.value)
        assert SECRET not in repr(source)


class TestChoice:
    OPTIONS = {"taxes": "all things taxes", "schools": None, "none": "None of these"}

    def test_choice_request_and_answer(self) -> None:
        seen: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(json.loads(request.content))
            return httpx.Response(
                200,
                json=answers(
                    route={
                        "type": "choice",
                        "choice": "taxes",
                        "confidence": 0.7,
                        "probabilities": {"taxes": 0.8, "schools": 0.15, "none": 0.05},
                    }
                ),
            )

        source, _ = source_for(handler)
        answer = source.choose(LEVY, "Which topic fits best?", self.OPTIONS)

        asked = seen[0]["questions"]["route"]
        assert asked["type"] == "choice"
        assert list(asked["criteria"]) == ["taxes", "schools", "none"]
        assert asked["criteria"]["schools"] is None
        assert answer.choice == "taxes"
        assert answer.probabilities == {"taxes": 0.8, "schools": 0.15, "none": 0.05}

    @pytest.mark.parametrize(
        "route",
        [
            {"type": "noul", "noul": 0.5},
            {"type": "choice", "choice": "taxes", "probabilities": {"taxes": 1.0}},
            {
                "type": "choice",
                "choice": "roads",
                "probabilities": {"taxes": 0.5, "schools": 0.3, "none": 0.2},
            },
        ],
    )
    def test_a_choice_that_does_not_match_the_options_is_refused(
        self, route: dict[str, Any]
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=answers(route=route))

        source, _ = source_for(handler)
        with pytest.raises(JudgmentUnavailable):
            source.choose(LEVY, "Which topic fits best?", self.OPTIONS)


class TestConstruction:
    @pytest.mark.parametrize("model", ["jev-latest", "jev-preview", "jev-1.14", "gpt"])
    def test_aliases_are_rejected(self, model: str) -> None:
        with pytest.raises(ValueError, match="versioned"):
            JevSource(SECRET, model=model)

    def test_a_key_is_required(self) -> None:
        with pytest.raises(ValueError):
            JevSource("")

    def test_attempts_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            JevSource(SECRET, attempts=0)


class TestReadApiKey:
    def test_environment_wins_over_the_file(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.local"
        env_file.write_text(f"{API_KEY_VARIABLE}=from-file\n", encoding="utf-8")
        assert read_api_key(env_file, {API_KEY_VARIABLE: "from-env"}) == "from-env"

    def test_file_is_read_when_the_environment_is_empty(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.local"
        env_file.write_text(
            f'# comment\nOTHER=1\n{API_KEY_VARIABLE} = "quoted-key"\n', encoding="utf-8"
        )
        assert read_api_key(env_file, {}) == "quoted-key"

    def test_missing_everywhere_is_none(self, tmp_path: Path) -> None:
        assert read_api_key(tmp_path / "absent", {}) is None
        assert read_api_key(None, {}) is None

    def test_an_empty_value_is_none(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.local"
        env_file.write_text(f"{API_KEY_VARIABLE}=\n", encoding="utf-8")
        assert read_api_key(env_file, {API_KEY_VARIABLE: "  "}) is None


class TestNesting:
    FROGS = create_category("tree frogs in the Amazon")
    ENVIRONMENT = create_category("the environment")

    def test_one_yes_no_question_per_ordered_pair(self) -> None:
        seen: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(json.loads(request.content))
            return httpx.Response(
                200, json=answers(pair_0=noul(0.96), pair_1=noul(0.03))
            )

        source, _ = source_for(handler)
        judged = source.judge_nesting(
            [(self.FROGS, self.ENVIRONMENT), (self.ENVIRONMENT, self.FROGS)]
        )

        body = seen[0]
        assert isinstance(body["state"], str) and "topics" in body["state"]
        assert list(body["questions"]) == ["pair_0", "pair_1"]
        first = body["questions"]["pair_0"]["instructions"]
        assert "Topic A: tree frogs in the Amazon." in first
        assert "Topic B: the environment." in first
        assert judged[(self.FROGS.id, self.ENVIRONMENT.id)].probability == 0.96
        assert judged[(self.ENVIRONMENT.id, self.FROGS.id)].probability == 0.03

    def test_no_pairs_means_no_request(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be sent")

        source, _ = source_for(handler)
        assert source.judge_nesting([]) == {}
        assert source.requests == 0

    def test_a_missing_answer_is_refused(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=answers(pair_0=noul(0.9)))

        source, _ = source_for(handler)
        with pytest.raises(JudgmentUnavailable):
            source.judge_nesting(
                [(self.FROGS, self.ENVIRONMENT), (self.ENVIRONMENT, self.FROGS)]
            )
