"""Replay completed v1 journal forecasts and compare v2 against their original evidence."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from preferences import journal_reasoning as v1
from preferences import journal_reasoning_v2 as v2
from preferences.journal_forecast import Forecast, JournalMeasure, JournalRequest


class Probe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    effect: str = Field(min_length=1, max_length=2500)
    expected_source: UUID
    expected_direction: Literal["yes", "no"]


class RegressionCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    history_count: int = Field(ge=0)
    replayed_baseline_yes: float = Field(ge=0, le=1)
    # An empty list with allow_no_match=True explicitly requires a neutral case.
    top_sources: list[UUID]
    allow_no_match: bool = False
    excluded_sources: list[UUID] = Field(default_factory=list)
    require_reason_from: list[UUID] = Field(default_factory=list)
    probes: list[Probe] = Field(default_factory=list)


def check_probe(probe: Probe, original: JournalRequest, verbose: bool) -> bool:
    """Change the proposal while keeping the original pre-vote history fixed."""
    packet = JournalMeasure(
        title="Synthetic policy comparison", sourceUrl="https://example.invalid/local-regression",
        text=f"The proposal concerns {probe.effect}.", familiar=False,
        yesMeaning=f'A "yes" vote supported {probe.effect}.',
        noMeaning=f'A "no" vote opposed {probe.effect}.',
    )
    request = original.model_copy(update={"measure": packet})
    if probe.expected_source not in {row.id for row in request.history}:
        raise ValueError("The probe references a source outside the original evidence.")
    arms = v2.paired_forecast(request)
    matches = v2.ranked_cases(packet, request.history)
    expected_sign = 1 if probe.expected_direction == "yes" else -1
    passed = bool(matches and matches[0].item.id == probe.expected_source and
                  (arms.reasoning.probabilityYes - .5) * expected_sign > 0)
    print(f"  Unscored synthetic probe | {probe.effect}")
    print(f"    P(Yes) {arms.reasoning.probabilityYes:.1%} with reasons, "
          f"{arms.withoutReasoning.probabilityYes:.1%} votes only. "
          f"Leading precedent: {matches[0].item.measure.title if matches else 'none'}.")
    if verbose:
        print(f"    {arms.reasoning.explanation}")
    print("    PASS" if passed else "    FAIL | Expected source or lean changed")
    return passed


def check_case(case: RegressionCase, data: dict, verbose: bool) -> tuple[bool, list[bool]]:
    request = JournalRequest.model_validate(data["request"])
    saved = Forecast.model_validate(data["locked"])
    if request.id != case.id or len(request.history) != case.history_count:
        raise ValueError("The selected case does not match its pinned evidence count or ID.")
    old = v1.paired_forecast(request)
    new = v2.paired_forecast(request)
    if saved != old.reasoning:
        raise ValueError(f"{request.measure.title}: unable to reproduce the original locked v1 forecast.")
    if old.baseline != new.baseline or new.baseline.probabilityYes != case.replayed_baseline_yes:
        raise ValueError(f"{request.measure.title}: the original baseline changed.")
    matches = v2.ranked_cases(request.measure, request.history)
    matched = {candidate.item.id for candidate in matches}
    history_ids = {row.id for row in request.history}
    expectations = set(case.top_sources + case.excluded_sources + case.require_reason_from)
    if not (matched | expectations) <= history_ids:
        raise ValueError("A regression references a source outside the original evidence.")
    failures = []
    if matches:
        if matches[0].item.id not in case.top_sources:
            failures.append("unexpected leading precedent")
    elif not case.allow_no_match or new.reasoning.probabilityYes != .5:
        failures.append("missing expected precedent or non-neutral estimate without one")
    if matched.intersection(case.excluded_sources):
        failures.append("an excluded precedent influenced the forecast")
    cited = {candidate.item.id for candidate in matches if candidate.citation}
    if case.require_reason_from and not cited.intersection(case.require_reason_from):
        failures.append("no matching explanation from an expected source")
    for candidate in matches:
        if candidate.citation:
            sources = [candidate.item.reasoning]
            if candidate.item.clarification:
                sources.append(candidate.item.clarification.answer)
            if not any(candidate.citation in source for source in sources):
                failures.append("a cited reason is absent from its eligible source")
    measure = request.measure
    swapped = measure.model_copy(update={"yesMeaning": measure.noMeaning, "noMeaning": measure.yesMeaning})
    reversed_forecast = v2.reasoning_forecast(request.model_copy(update={"measure": swapped}))
    if not math.isclose(reversed_forecast.probabilityYes, 1 - new.reasoning.probabilityYes, abs_tol=1e-6):
        failures.append("swapping the outcome descriptions did not reverse the forecast probabilities")

    # The target's recorded vote is available only for reporting, outside the
    # model request. Its own reasoning and follow-up are never exported.
    print(f"{request.measure.title} | vote {data['vote']} | {len(request.history)} prior")
    print(f"  P(Yes)  baseline {old.baseline.probabilityYes:.1%}  "
          f"v1 locked {saved.probabilityYes:.1%}  v1 votes only {old.withoutReasoning.probabilityYes:.1%}  "
          f"v2 votes only {new.withoutReasoning.probabilityYes:.1%}  v2 with reasons {new.reasoning.probabilityYes:.1%}")
    print(f"  Leading precedent: {matches[0].item.measure.title if matches else 'none'}")
    if verbose:
        for match in matches:
            print(f"    {match.score:+.3f} {match.item.measure.title} | {', '.join(match.matched_terms)}")
            if match.citation:
                print(f"      {match.citation}")
        print(f"  {new.reasoning.explanation}")
    print("  " + ("FAIL | " + " | ".join(failures) if failures else "PASS"))
    return not failures, [check_probe(probe, request, verbose) for probe in case.probes]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Private JSON array of pinned cases and expected precedents")
    parser.add_argument("--journal-dir", type=Path, help="Defaults to the local journal's storage directory")
    parser.add_argument("--verbose", action="store_true", help="Include private source excerpts and match details")
    args = parser.parse_args()
    cases = [RegressionCase.model_validate(row) for row in json.loads(args.manifest.read_text(encoding="utf-8"))]
    ids = [str(case.id) for case in cases]
    if not ids or len(set(ids)) != len(ids):
        parser.error("Specify at least one case and pin each case only once.")
    env = os.environ.copy()
    if args.journal_dir:
        env["PERSONAL_JOURNAL_DIR"] = str(args.journal_dir.resolve())
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["node", "--disable-warning=ExperimentalWarning", "--disable-warning=MODULE_TYPELESS_PACKAGE_JSON",
         "--experimental-strip-types", "scripts/read-journal-regression-cases.mjs"],
        cwd=root, env=env, input=json.dumps(ids).encode("utf-8"), stdout=subprocess.PIPE, check=True,
    )
    records = json.loads(result.stdout)
    results = [check_case(case, row, args.verbose) for case, row in zip(cases, records, strict=True)]
    passed = sum(ok for ok, _ in results)
    probes = [ok for _, items in results for ok in items]
    print(f"{passed}/{len(cases)} retrospective regression cases passed.")
    if probes:
        print(f"{sum(probes)}/{len(probes)} unscored synthetic probes matched the expected source and direction.")
    return int(passed != len(cases) or not all(probes))


if __name__ == "__main__":
    raise SystemExit(main())
