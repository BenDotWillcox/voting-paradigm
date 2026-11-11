"""
Hosted Jev (TypeSafe's decision model) as a judgment source.

This is the one module in the package that talks to the network, and the
package does not import it: callers that want live judgments import
`delegation.jev` themselves. Everything else reads recorded judgments.

Wire format, from TypeSafe's API reference as read on 2026-11-10:

  POST https://api.typesafe.ai/v1/systemone
  Authorization: Bearer <key>
  {"model": ..., "state": ..., "questions": {name: {"type": "noul", ...}}}
  -> {"model": ..., "answers": {name: {"type": "noul", "noul": 0.98}},
      "usage": {"input_tokens": ..., "output_tokens": ...}}

Rules this client holds itself to:

  - The model is always a versioned id, never an alias, and an answer from
    any other model is refused. Aliases move when TypeSafe ships a release.
  - The API key is read from the environment or an env file, sent only in
    the Authorization header, and never logged, stored or put in an error.
  - Error messages carry the HTTP status and nothing from the response body.
  - Transient failures are retried a bounded number of times; anything else
    raises JudgmentUnavailable, and the caller fails closed.

Only question text and category text are sent. No person, delegation or
vote leaves the machine.
"""

from __future__ import annotations

import math
import os
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .judgments import (
    JudgmentUnavailable,
    SourceAnswer,
    category_instruction,
    question_state,
)
from .nesting import NESTING_STATE, nesting_instruction
from .types import Category, CategoryId, Question

# The pinned model. Recorded judgments belong to the model that produced them,
# so changing this starts a fresh set and needs the threshold re-checked.
JEV_MODEL = "jev-1.14.0"
JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
API_KEY_VARIABLE = "TYPESAFE_API_KEY"

_VERSIONED_MODEL = re.compile(r"^jev-\d+\.\d+\.\d+$")
# Statuses worth another attempt: timeouts, rate limits, and server trouble
# (529 is TypeSafe's "temporarily overloaded").
_RETRY_STATUSES = frozenset({408, 429, 500, 502, 503, 504, 529})
_LONGEST_WAIT = 30.0


def read_api_key(
    env_file: Path | None = None, environ: Mapping[str, str] | None = None
) -> str | None:
    """
    Find the TypeSafe API key without revealing it.

    The environment is checked first, then `KEY=value` lines in the env
    file. Surrounding quotes are dropped.

    Returns:
        The key, or None when it is not set anywhere.
    """
    source = os.environ if environ is None else environ
    value = source.get(API_KEY_VARIABLE, "").strip()
    if value:
        return value
    if env_file is None or not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, separator, raw = line.partition("=")
        if separator and name.strip() == API_KEY_VARIABLE:
            cleaned = raw.strip().strip("\"'")
            return cleaned or None
    return None


@dataclass(frozen=True)
class ChoiceAnswer:
    """The answer to a single choice question."""

    choice: str
    probabilities: dict[str, float]
    answered_by: str


class JevSource:
    """
    Judgments from hosted Jev.

    Raises:
        ValueError: If the key is empty, the model is not a versioned id, or
            attempts is not positive
    """

    def __init__(
        self,
        api_key: str,
        *,
        model: str = JEV_MODEL,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
        attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise ValueError("An API key is required")
        if not _VERSIONED_MODEL.match(model):
            raise ValueError(
                f"{model!r} is not a versioned Jev model id; aliases such as "
                "jev-latest move between releases and cannot be recorded against"
            )
        if attempts < 1:
            raise ValueError("attempts must be at least 1")
        self._api_key = api_key
        self._model = model
        self._client = client if client is not None else httpx.Client(timeout=timeout)
        self._attempts = attempts
        self._sleep = sleep
        # Running totals, for reporting what a run actually used
        self.requests = 0
        self.input_tokens = 0

    def __repr__(self) -> str:
        return f"JevSource(model={self._model!r})"

    @property
    def model(self) -> str:
        return self._model

    def close(self) -> None:
        """Release the HTTP client."""
        self._client.close()

    def judge(
        self, question: Question, categories: Sequence[Category]
    ) -> dict[CategoryId, SourceAnswer]:
        """
        Ask one yes/no question per category about one ballot question.

        The category id is the question name; per TypeSafe's docs the model
        never sees it.

        Raises:
            JudgmentUnavailable: If the request failed, another model
                answered, or any answer is missing or malformed
        """
        if not categories:
            return {}
        answers = self._ask(
            question_state(question),
            {
                category.id: {
                    "type": "noul",
                    "instructions": category_instruction(category),
                }
                for category in categories
            },
        )
        judged: dict[CategoryId, SourceAnswer] = {}
        for category in categories:
            answer = answers.get(category.id)
            if not isinstance(answer, dict) or answer.get("type") != "noul":
                raise JudgmentUnavailable("Jev left a question unanswered")
            judged[category.id] = SourceAnswer(
                probability=_probability(answer.get("noul")),
                answered_by=self._model,
            )
        return judged

    def judge_nesting(
        self, pairs: Sequence[tuple[Category, Category]]
    ) -> dict[tuple[CategoryId, CategoryId], SourceAnswer]:
        """
        Ask, for each (narrow, broad) pair, whether narrow sits inside broad.

        All pairs go in one request as separate yes/no questions, which
        TypeSafe answers independently of one another.

        Raises:
            JudgmentUnavailable: If the request failed, another model
                answered, or any answer is missing or malformed
        """
        if not pairs:
            return {}
        answers = self._ask(
            NESTING_STATE,
            {
                f"pair_{index}": {
                    "type": "noul",
                    "instructions": nesting_instruction(narrow, broad),
                }
                for index, (narrow, broad) in enumerate(pairs)
            },
        )
        judged: dict[tuple[CategoryId, CategoryId], SourceAnswer] = {}
        for index, (narrow, broad) in enumerate(pairs):
            answer = answers.get(f"pair_{index}")
            if not isinstance(answer, dict) or answer.get("type") != "noul":
                raise JudgmentUnavailable("Jev left a question unanswered")
            judged[(narrow.id, broad.id)] = SourceAnswer(
                probability=_probability(answer.get("noul")),
                answered_by=self._model,
            )
        return judged

    def choose(
        self,
        question: Question,
        instructions: str,
        options: Mapping[str, str | None],
    ) -> ChoiceAnswer:
        """
        Ask one choice question about a ballot question.

        This is the comparison arm of the router evaluation: one question
        listing a voter's categories plus a "none" option. The routing rule
        itself uses judge().

        Args:
            question: The ballot question
            instructions: What is being chosen
            options: Option name to its description, or None for a name that
                speaks for itself. The order is the order Jev sees.

        Raises:
            JudgmentUnavailable: If the request failed, another model
                answered, or the answer does not cover every option
        """
        answers = self._ask(
            question_state(question),
            {
                "route": {
                    "type": "choice",
                    "instructions": instructions,
                    "criteria": dict(options),
                }
            },
        )
        answer = answers.get("route")
        if not isinstance(answer, dict) or answer.get("type") != "choice":
            raise JudgmentUnavailable("Jev left the choice unanswered")
        reported = answer.get("probabilities")
        if not isinstance(reported, dict) or set(reported) != set(options):
            raise JudgmentUnavailable("Jev's choice does not cover the options")
        choice = answer.get("choice")
        if choice not in options:
            raise JudgmentUnavailable("Jev chose an option that was not offered")
        return ChoiceAnswer(
            choice=str(choice),
            probabilities={name: _probability(reported[name]) for name in options},
            answered_by=self._model,
        )

    def _ask(
        self, state: object, questions: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """Send one request and return its answers, retrying transient failures."""
        payload = {
            "model": self._model,
            "state": state,
            "questions": questions,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        problem = "no attempt was made"

        for attempt in range(self._attempts):
            self.requests += 1
            wait = min(0.5 * 2 ** (attempt + 1), _LONGEST_WAIT)
            try:
                response = self._client.post(
                    JEV_ENDPOINT, json=payload, headers=headers
                )
            except httpx.HTTPError as error:
                problem = f"the request failed ({type(error).__name__})"
            else:
                if response.status_code == 200:
                    return self._read(response)
                if response.status_code not in _RETRY_STATUSES:
                    raise JudgmentUnavailable(
                        f"Jev returned HTTP {response.status_code}"
                    )
                problem = f"HTTP {response.status_code}"
                asked = _retry_after(response)
                if asked is not None:
                    wait = asked
            if attempt + 1 < self._attempts:
                self._sleep(wait)

        raise JudgmentUnavailable(
            f"Jev was unavailable after {self._attempts} attempts: {problem}"
        )

    def _read(self, response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError:
            raise JudgmentUnavailable("Jev's response was not JSON") from None
        if not isinstance(body, dict) or not isinstance(body.get("answers"), dict):
            raise JudgmentUnavailable("Jev's response had no answers")
        answered_by = body.get("model")
        if answered_by != self._model:
            raise JudgmentUnavailable(
                f"The response came from {answered_by!r}, not the pinned "
                f"{self._model!r}"
            )
        usage = body.get("usage")
        if isinstance(usage, dict) and isinstance(usage.get("input_tokens"), int):
            self.input_tokens += usage["input_tokens"]
        answers: dict[str, Any] = body["answers"]
        return answers


def _probability(value: object) -> float:
    """A number from Jev, checked to be a probability."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JudgmentUnavailable("Jev returned a probability that is not a number")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise JudgmentUnavailable("Jev returned a probability outside 0 to 1")
    return number


def _retry_after(response: httpx.Response) -> float | None:
    """Seconds the server asked us to wait, when it said so in plain seconds."""
    try:
        seconds = float(response.headers.get("retry-after", ""))
    except ValueError:
        return None
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return min(seconds, _LONGEST_WAIT)
