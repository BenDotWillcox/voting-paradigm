"""Collect and report the demo 5 router evaluation.

Commands:
    plan      Print what a full collection would send. No network.
    smoke     Send one request (the first question against every category)
              to check the key and the wire format. Needs --live.
    collect   Send everything not yet recorded. Resumable. Needs --live.
    report    Write summary.json, config.json and metadata.json from the
              recorded answers. No network.

`smoke` and `collect` call hosted Jev and cost money, so they refuse to run
without --live. The API key is read from the environment or .env.local and
is never printed.

Recorded answers live in eval/benchmarks/delegation_router_v1/:
- judgments.jsonl   one yes/no judgment per (question, category); first
                    response wins and is never replaced
- choice.jsonl      the single-choice arm, one answer per voter case
- repeats.jsonl     the same judgments asked several times
- nesting.jsonl     whether each category sits inside each of the others

Usage:
    python -m eval.run_delegation_router_eval plan
    python -m eval.run_delegation_router_eval smoke --live
    python -m eval.run_delegation_router_eval collect --live
    python -m eval.run_delegation_router_eval report
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from delegation import NestingStore, gather_nesting
from delegation.nesting import NESTING_INSTRUCTION, NESTING_STATE
from delegation.judgments import (
    NOUL_INSTRUCTION,
    JudgmentStore,
    JudgmentUnavailable,
    gather_judgments,
)

from .delegation_router import (
    CHOICE_INSTRUCTION,
    FIXTURE_PATH,
    NONE_OPTION,
    STUDY_ID,
    USD_PER_MILLION_INPUT_TOKENS,
    ChoiceRecord,
    RepeatRecord,
    RouterEvalConfig,
    RouterFixture,
    choice_options,
    load_fixture,
    ordered_pairs,
    plan,
    repeat_questions,
    summarize,
    voter_cases,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = REPO_ROOT / "eval" / "benchmarks" / STUDY_ID
ENV_FILE = REPO_ROOT / ".env.local"
JUDGMENTS = "judgments.jsonl"
CHOICES = "choice.jsonl"
REPEATS = "repeats.jsonl"
NESTING = "nesting.jsonl"
RECORDED = (JUDGMENTS, CHOICES, REPEATS, NESTING)
# Source the reported numbers depend on, besides the recorded answers
STUDY_SOURCES = (
    "eval/delegation_router.py",
    "eval/run_delegation_router_eval.py",
    "eval/fixtures/delegation_router_v1.json",
)
# Stop a collection after this many requests in a row have failed
FAILURES_BEFORE_STOPPING = 3


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plan")
    commands.add_parser("report")
    for name in ("smoke", "collect"):
        paid = commands.add_parser(name)
        paid.add_argument("--live", action="store_true")
        paid.add_argument("--max-requests", type=int, default=None)
    args = parser.parse_args(argv)

    fixture = load_fixture()
    config = RouterEvalConfig()
    if args.command == "plan":
        print(json.dumps(plan(fixture, config), indent=2))
        return 0
    if args.command == "report":
        return report(fixture, config)
    if not args.live:
        raise SystemExit(
            f"'{args.command}' calls hosted Jev and costs money; pass --live"
        )
    return collect(
        fixture, config, smoke=args.command == "smoke", cap=args.max_requests
    )


# ---------------------------------------------------------------------------
# Collecting (the only part that uses the network)
# ---------------------------------------------------------------------------


def collect(
    fixture: RouterFixture, config: RouterEvalConfig, *, smoke: bool, cap: int | None
) -> int:
    # Imported here so plan and report never load the HTTP client.
    from delegation.jev import JEV_MODEL, JevSource, read_api_key

    key = read_api_key(ENV_FILE)
    if key is None:
        raise SystemExit("TYPESAFE_API_KEY is not set in the environment or .env.local")
    if cap is None:
        cap = 1 if smoke else 2 * int(plan(fixture, config)["total_requests"])

    source = JevSource(key)
    collector = _Collector(fixture, config, source, JEV_MODEL, cap)
    try:
        if smoke:
            complete = collector.judge(fixture.questions[:1])
        else:
            complete = (
                collector.judge(fixture.questions)
                and collector.choose()
                and collector.repeat()
                and collector.nest()
            )
    finally:
        source.close()
        cost = source.input_tokens * USD_PER_MILLION_INPUT_TOKENS / 1_000_000
        print(
            f"requests sent: {source.requests}; input tokens billed: "
            f"{source.input_tokens}; cost at list price: ${cost:.4f}"
        )
    if smoke and complete:
        _print_smoke(fixture)
    return 0 if complete else 1


class _Collector:
    """Runs the three collection phases, stopping at the request cap."""

    def __init__(
        self,
        fixture: RouterFixture,
        config: RouterEvalConfig,
        source: Any,
        model: str,
        cap: int,
    ) -> None:
        self.fixture = fixture
        self.config = config
        self.source = source
        self.model = model
        self.cap = cap
        self.failures_in_a_row = 0
        self.categories = [entry.category for entry in fixture.categories]

    def _may_send(self) -> bool:
        if self.source.requests >= self.cap:
            print(f"stopped: the request cap of {self.cap} was reached")
            return False
        if self.failures_in_a_row >= FAILURES_BEFORE_STOPPING:
            print(f"stopped: {self.failures_in_a_row} requests failed in a row")
            return False
        return True

    def _note(self, failure: str | None) -> None:
        if failure is None:
            self.failures_in_a_row = 0
        else:
            self.failures_in_a_row += 1
            print(f"failed: {failure}")

    def judge(self, questions: Sequence[Any]) -> bool:
        """One yes/no judgment per (question, category), recorded as it arrives."""
        store = JudgmentStore(BENCHMARK / JUDGMENTS)
        for labelled in questions:
            pending = gather_judgments(
                [labelled.question], self.categories, store, model=self.model
            ).missing
            if not pending:
                continue
            if not self._may_send():
                return False
            result = gather_judgments(
                [labelled.question],
                self.categories,
                store,
                model=self.model,
                source=self.source,
                batch_size=len(self.categories),
            )
            self._note(result.failures[0] if result.failures else None)
        return self.failures_in_a_row == 0

    def choose(self) -> bool:
        """The single-choice arm: one choice question per voter case."""
        path = BENCHMARK / CHOICES
        done = {(record.question, record.keys) for record in load_choices(path)}
        text_to_key = {e.category.text: e.key for e in self.fixture.categories}
        for case in voter_cases(self.fixture, self.config):
            if (case.question, case.keys) in done:
                continue
            if not self._may_send():
                return False
            question = self.fixture.labelled(case.question).question
            try:
                answer = self.source.choose(
                    question, CHOICE_INSTRUCTION, choice_options(self.fixture, case)
                )
            except JudgmentUnavailable as error:
                self._note(f"{case.question}: {error}")
                continue
            self._note(None)
            _append(
                path,
                ChoiceRecord(
                    question=case.question,
                    keys=case.keys,
                    choice=text_to_key.get(answer.choice),
                    probabilities={
                        text_to_key.get(name, NONE_OPTION): probability
                        for name, probability in answer.probabilities.items()
                    },
                ),
            )
        return self.failures_in_a_row == 0

    def repeat(self) -> bool:
        """Ask the same judgments several times, without recording them as judgments."""
        path = BENCHMARK / REPEATS
        done = {record.question for record in load_repeats(path)}
        for labelled in repeat_questions(self.fixture, self.config):
            if labelled.question.id in done:
                continue
            runs = []
            for _ in range(self.config.repeats):
                if not self._may_send():
                    return False
                try:
                    runs.append(self.source.judge(labelled.question, self.categories))
                except JudgmentUnavailable as error:
                    self._note(f"{labelled.question.id}: {error}")
                    break
                self._note(None)
            if len(runs) < self.config.repeats:
                continue
            for entry in self.fixture.categories:
                _append(
                    path,
                    RepeatRecord(
                        question=labelled.question.id,
                        category=entry.key,
                        probabilities=tuple(
                            run[entry.category.id].probability for run in runs
                        ),
                    ),
                )
        return self.failures_in_a_row == 0

    def nest(self) -> bool:
        """Ask whether each category sits inside each of the others."""
        store = NestingStore(BENCHMARK / NESTING)
        for narrow in self.categories:
            pairs = [
                (narrow, broad) for broad in self.categories if broad.id != narrow.id
            ]
            if not gather_nesting(pairs, store, model=self.model).missing:
                continue
            if not self._may_send():
                return False
            result = gather_nesting(
                pairs,
                store,
                model=self.model,
                source=self.source,
                batch_size=len(pairs),
            )
            self._note(result.failures[0] if result.failures else None)
        return self.failures_in_a_row == 0


def _print_smoke(fixture: RouterFixture) -> None:
    """Show the smoke request's highest scores, so the wiring can be eyeballed."""
    from delegation.jev import JEV_MODEL

    labelled = fixture.questions[0]
    store = JudgmentStore(BENCHMARK / JUDGMENTS)
    judgments = gather_judgments(
        [labelled.question],
        [e.category for e in fixture.categories],
        store,
        model=JEV_MODEL,
    ).judgments
    ranked = sorted(
        (
            (score, fixture.key_of(category))
            for (_, category), score in judgments.items()
        ),
        reverse=True,
    )
    print(f"{labelled.question.id} '{labelled.question.title}': highest scores")
    for score, key in ranked[:5]:
        marker = "acceptable" if key in labelled.acceptable else ""
        print(f"  {score:.3f}  {key}  {marker}")


# ---------------------------------------------------------------------------
# Recorded answers
# ---------------------------------------------------------------------------


def _append(path: Path, record: ChoiceRecord | RepeatRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as lines:
        lines.write(json.dumps(asdict(record), sort_keys=True) + "\n")


def _lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as lines:
        return [json.loads(line) for line in lines if line.strip()]


def load_choices(path: Path) -> list[ChoiceRecord]:
    return [
        ChoiceRecord(
            question=item["question"],
            keys=tuple(item["keys"]),
            choice=item["choice"],
            probabilities=item["probabilities"],
        )
        for item in _lines(path)
    ]


def load_repeats(path: Path) -> list[RepeatRecord]:
    return [
        RepeatRecord(
            question=item["question"],
            category=item["category"],
            probabilities=tuple(item["probabilities"]),
        )
        for item in _lines(path)
    ]


# ---------------------------------------------------------------------------
# Reporting (no network)
# ---------------------------------------------------------------------------


def report(fixture: RouterFixture, config: RouterEvalConfig) -> int:
    from delegation.jev import JEV_MODEL

    if not (BENCHMARK / JUDGMENTS).exists():
        raise SystemExit(f"No recorded judgments in {BENCHMARK}; run collect first")

    store = JudgmentStore(BENCHMARK / JUDGMENTS)
    judgments = gather_judgments(
        [labelled.question for labelled in fixture.questions],
        [entry.category for entry in fixture.categories],
        store,
        model=JEV_MODEL,
    ).judgments
    containment = gather_nesting(
        ordered_pairs(fixture), NestingStore(BENCHMARK / NESTING), model=JEV_MODEL
    ).probabilities
    summary = summarize(
        fixture,
        config,
        judgments,
        load_choices(BENCHMARK / CHOICES),
        load_repeats(BENCHMARK / REPEATS),
        containment,
    )
    outputs = {
        "config.json": _json_bytes(
            {
                **asdict(config),
                "model": JEV_MODEL,
                "judgment_instruction": NOUL_INSTRUCTION,
                "choice_instruction": CHOICE_INSTRUCTION,
                "nesting_state": NESTING_STATE,
                "nesting_instruction": NESTING_INSTRUCTION,
                "fixture": FIXTURE_PATH.relative_to(REPO_ROOT).as_posix(),
            }
        ),
        "summary.json": _json_bytes({"model": JEV_MODEL, **summary}),
    }
    metadata = {
        "study": STUDY_ID,
        "generator": "python -m eval.run_delegation_router_eval report",
        "python": platform.python_version(),
        "model": JEV_MODEL,
        "source_sha256": _source_sha256(),
        "recorded": {
            name: _sha256((BENCHMARK / name).read_bytes().replace(b"\r\n", b"\n"))
            for name in RECORDED
            if (BENCHMARK / name).exists()
        },
        "outputs": {name: _sha256(body) for name, body in outputs.items()},
    }
    outputs["metadata.json"] = _json_bytes(metadata)
    for name, body in outputs.items():
        (BENCHMARK / name).write_bytes(body)

    headline = summary["router_at_operating_threshold"]
    nested = summary["nested_categories"]
    print(json.dumps({"router": headline, "nested": nested}, indent=2))
    return 0


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_sha256() -> str:
    """The delegation package (tests excluded) and the study's own files."""
    digest = hashlib.sha256()
    paths = [
        path
        for path in (REPO_ROOT / "delegation").rglob("*.py")
        if "tests" not in path.parts
    ]
    paths += [REPO_ROOT / name for name in STUDY_SOURCES]
    for path in sorted(paths, key=lambda p: p.relative_to(REPO_ROOT).as_posix()):
        digest.update(path.relative_to(REPO_ROOT).as_posix().encode("utf-8") + b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
