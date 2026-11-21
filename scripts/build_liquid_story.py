#!/usr/bin/env python3
"""Build the static data for the liquid-democracy walkthrough (/liquid).

Reads only committed files: the frozen benchmark's summaries in
eval/benchmarks/delegation_frontier_v1/ and the illustrative city that
scripts/build_liquid_example_city.py writes. Writes to
public/data/liquid-story/:

- measures.json  per turnout level, every arrangement's fidelity, contrary
                 and no-ballot shares and overhead, averaged over the 200
                 primary cities; the frozen protocol's constants; and the
                 pre-registered verdict, word for word
- results.json   per turnout level, the frozen result (liquid minus the
                 representative with its band, the cap-only curve, the share
                 of cities under the cap, liquid's and the proxy's), the
                 declared ladder and the attendance frontier; the threshold
                 and the protocol's rules; every sweep point in the
                 benchmark's own panels; and the router's measured errors
                 (eval/benchmarks/delegation_router_v1)
- exploratory.json  the analyses made after the freeze, labelled so: liquid's
                 handover curve and the wrong-ballot scores
                 (eval/benchmarks/delegation_handover_v1), the everyone-votes
                 reference point (eval/benchmarks/delegation_everyone_votes_v1),
                 the fallback study (eval/benchmarks/delegation_fallback_v1),
                 and the personal agent's bars (proposal arithmetic on the
                 frozen shares)
- manifest.json  SHA-256 of every input and output, city.json included

Every number the page quotes is read from these files, never typed into the
page. Deterministic: the same inputs give byte-identical outputs.

Usage:
    python scripts/build_liquid_story.py
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Final

ROOT: Final = Path(__file__).resolve().parents[1]
FRONTIER: Final = ROOT / "eval" / "benchmarks" / "delegation_frontier_v1"
ROUTER: Final = ROOT / "eval" / "benchmarks" / "delegation_router_v1"
ROUTER_FIXTURE: Final = ROOT / "eval" / "fixtures" / "delegation_router_v1.json"
HANDOVER: Final = ROOT / "eval" / "benchmarks" / "delegation_handover_v1"
# The exploratory benchmark's committed summaries
HANDOVER_INPUTS: Final = ("curve.csv", "wrong_ballot.csv", "manifest.json")
EVERYONE: Final = ROOT / "eval" / "benchmarks" / "delegation_everyone_votes_v1"
EVERYONE_INPUTS: Final = ("measures.csv", "contrasts.csv", "cap.csv", "manifest.json")
FALLBACK: Final = ROOT / "eval" / "benchmarks" / "delegation_fallback_v1"
FALLBACK_INPUTS: Final = ("measures.csv", "levels.csv", "hypothesis.json", "manifest.json")
# What the story reads of liquid with the default at each level
FALLBACK_FIELDS: Final = ("fidelity", "contrary_share", "none_share", "overhead", "loop_share", "empty_record_fidelity")
OUT: Final = ROOT / "public" / "data" / "liquid-story"
CITY: Final = OUT / "city.json"
ARTIFACT_VERSION: Final = 1
PRIMARY: Final = "primary: primary settings"
# The page's arrangements, in its order
ARRANGEMENTS: Final = ("full_turnout", "direct", "representative", "proxy", "liquid")
FIELDS: Final = ("fidelity", "contrary_share", "none_share", "overhead")
# Measures the edges and attendance sections read; blank where an
# arrangement has none (a representative has no loops), kept as null
EXTRA_FIELDS: Final = (
    "empty_record_share",
    "empty_record_fidelity",
    "light_record_share",
    "light_record_fidelity",
    "loop_share",
    "fidelity_kept",
    "resolver_attendance",
    # Concentration, poor representation, the cold start and outcomes (§10–11)
    "mean_largest_share",
    "max_largest_share",
    "share_below_half",
    "below_half_none_share",
    "below_half_contrary_share",
    "lifecycle_overhead",
    "outcome_agreement",
    # A chosen delegate's ballots, for the personal agent's bar (§13)
    "fidelity_resolved",
    "delegated_share",
    "lost_share",
)
INPUTS: Final = (
    "measures.csv",
    "thresholds.csv",
    "levels.csv",
    "decomposition.csv",
    "frontier.csv",
    "primary_report.json.gz",
    "manifest.json",
)


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _optional(raw: str) -> float | None:
    return None if raw == "" else float(raw)


def _results(grid: list[float], protocol: dict[str, Any], threshold: dict[str, str]) -> dict[str, Any]:
    """The result (Figure 1), the ladder and the attendance frontier (Figure 2), per level."""
    levels_rows = {float(r["level"]): r for r in _rows(FRONTIER / "levels.csv") if r["point"] == PRIMARY}
    decomposition = [r for r in _rows(FRONTIER / "decomposition.csv") if r["point"] == PRIMARY]
    frontier = _rows(FRONTIER / "frontier.csv")
    with gzip.open(FRONTIER / "primary_report.json.gz", "rt", encoding="utf-8") as handle:
        report = json.load(handle)["points"][PRIMARY]["by_level"]
    levels: dict[str, Any] = {}
    for level in grid:
        row = levels_rows[level]
        levels[repr(level)] = {
            "cap_share": float(row["cap_share"]),
            "cap_meeting_cities": int(row["cap_meeting_cities"]),
            # The proxy's own share under the cap (the report's specialisation block)
            "proxy_cap_share": float(report[repr(level)]["specialisation"]["proxy_share"]),
            "h1": {f: float(row[f"h1_all_{f}"]) for f in ("estimate", "lower", "upper")},
            "band": {f: float(row[f"band_all_{f}"]) for f in ("lower", "upper")},
            "h1_cap": None if row["h1_cap_estimate"] == "" else {
                f: float(row[f"h1_cap_{f}"]) for f in ("estimate", "lower", "upper")
            },
            "band_cap": None if row["band_cap_lower"] == "" else {
                f: float(row[f"band_cap_{f}"]) for f in ("lower", "upper")
            },
            "direction": row["h1_direction"],
            "size": row["h1_size"],
            # Topic specialisation's own reading against its pre-set minimum
            "specialisation": {"direction": row["specialisation_direction"], "size": row["specialisation_size"]},
            "decomposition": {
                r["quantity"]: {f: float(r[f]) for f in ("estimate", "lower", "upper")}
                for r in decomposition
                if float(r["level"]) == level
            },
            "frontier": [
                {"floor": float(r["floor"]), **{f: float(r[f]) for f in ("estimate", "lower", "upper")}}
                for r in frontier
                if float(r["level"]) == level
            ],
        }
    rules = protocol["protocol"]
    return {
        "source": "eval/benchmarks/delegation_frontier_v1 (thresholds, levels, decomposition and frontier CSVs; "
        "primary_report.json.gz for the proxy's cap share)",
        "label": "frozen",
        "rules": {
            "cap": rules["cap"],
            "delta": rules["delta"],
            "feasible_share": rules["feasible_share"],
            "confidence": rules["confidence"],
        },
        "threshold": {
            "status": threshold["status"],
            "bracket": [float(threshold["bracket_low"]), float(threshold["bracket_high"])],
            "crossing": float(threshold["all_cities_interpolated"]),
            "confidence": [float(threshold["confidence_low"]), float(threshold["confidence_high"])],
            "first_supported": _optional(threshold["first_supported"]),
            "gate_holds": threshold["gate_holds"] == "true",
        },
        "levels": levels,
    }


def _bound(raw: str) -> float | None:
    """A threshold bound; null where the frozen confidence set is unbounded."""
    return None if raw in ("inf", "-inf", "") else float(raw)


def _sweeps(grid: list[float]) -> dict[str, Any]:
    """Every sweep point's curve, cap shares and threshold, in the benchmark's own panels."""
    sys.path.insert(0, str(ROOT))
    from eval.delegation_frontier import REFERENCE_KEY, STRUCTURAL_BASELINE  # noqa: PLC0415
    from eval.plot_delegation_frontier import SERIES_1, SERIES_2, SWEEP_PANELS  # noqa: PLC0415

    levels_rows = [r for r in _rows(FRONTIER / "levels.csv") if r["point"] != PRIMARY]
    thresholds = {r["point"]: r for r in _rows(FRONTIER / "thresholds.csv")}
    points: dict[str, Any] = {}
    # In the order the points appear in levels.csv: a set's order would change
    # between runs and break the byte-for-byte rebuild
    for key in dict.fromkeys(r["point"] for r in levels_rows):
        row = thresholds[key]
        at = {float(r["level"]): r for r in levels_rows if r["point"] == key}
        points[key] = {
            "family": row["family"],
            "label": row["label"],
            "cities": int(row["cities"]),
            "baseline": row["baseline"] or None,
            "verdict": row["verdict"],
            "status": row["status"],
            "crossing": _optional(row["all_cities_interpolated"]),
            "confidence": [_bound(row["confidence_low"]), _bound(row["confidence_high"])],
            "gate_holds": row["gate_holds"] == "true",
            "levels": {
                repr(level): {"h1": float(at[level]["h1_all_estimate"]), "cap_share": float(at[level]["cap_share"])}
                for level in grid
            },
        }
    accent = {SERIES_1: 0, SERIES_2: 1}
    panels = [
        {
            "title": title,
            "series": [
                {
                    "point": key,
                    "label": label,
                    "baseline": key in (REFERENCE_KEY, STRUCTURAL_BASELINE),
                    "accent": accent.get(color) if color else None,
                }
                for key, label, color in series
            ],
        }
        for title, series in SWEEP_PANELS
    ]
    return {"reference": REFERENCE_KEY, "structural_baseline": STRUCTURAL_BASELINE, "panels": panels, "points": points}


def _router_examples(operating: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Three voter cases from the router benchmark, routed again with the real
    rule at the operating threshold from the recorded judgments: the first
    correct delegation with three or more categories, the first false keep
    and the first false delegation, in the benchmark's own case order.
    Rebuilding every case's verdict must reproduce the published tally.
    """
    sys.path.insert(0, str(ROOT))
    from delegation.jev import JEV_MODEL  # noqa: PLC0415
    from delegation.judgments import JudgmentStore, gather_judgments  # noqa: PLC0415
    from eval.delegation_router import (  # noqa: PLC0415
        RouterEvalConfig,
        Verdict,
        judge_outcome,
        load_fixture,
        routed_key,
        voter_cases,
    )

    fixture = load_fixture(ROUTER_FIXTURE)
    config = RouterEvalConfig()
    judgments = gather_judgments(
        [labelled.question for labelled in fixture.questions],
        [entry.category for entry in fixture.categories],
        JudgmentStore(ROUTER / "judgments.jsonl"),
        model=JEV_MODEL,
    ).judgments
    probability = {
        (row["question"], row["category"]): float(row["probability"])
        for row in map(json.loads, (ROUTER / "judgments.jsonl").read_text(encoding="utf-8").splitlines())
    }
    threshold = config.operating_threshold
    verdicts = []
    for case in voter_cases(fixture, config):
        _, chosen = routed_key(fixture, case, judgments, threshold)
        verdicts.append((case, chosen, judge_outcome(fixture.labelled(case.question), case.keys, chosen)))
    counts = {v: sum(1 for _, _, verdict in verdicts if verdict is v) for v in Verdict}
    if (counts[Verdict.FALSE_DELEGATION], counts[Verdict.FALSE_KEEP]) != (
        operating["false_delegations"],
        operating["false_keeps"],
    ):
        raise ValueError("the rebuilt routing does not reproduce the router benchmark's tally")

    def first(verdict: Any, *, at_least: int = 1) -> dict[str, Any]:
        case, chosen, _ = next(c for c in verdicts if c[2] is verdict and len(c[0].keys) >= at_least)
        labelled = fixture.labelled(case.question)
        return {
            "verdict": verdict.value,
            "question": {"id": case.question, "title": labelled.question.title, "summary": labelled.question.summary},
            "categories": [
                {
                    "key": key,
                    "text": fixture.entry(key).category.text,
                    "probability": probability[(case.question, fixture.entry(key).category.id)],
                    "acceptable": key in labelled.acceptable,
                }
                for key in case.keys
            ],
            "chosen": chosen,
        }

    return [
        first(Verdict.CORRECT_DELEGATION, at_least=3),
        first(Verdict.FALSE_KEEP),
        first(Verdict.FALSE_DELEGATION),
    ]


def _router() -> dict[str, Any]:
    """The router's measured errors at every threshold (delegation_router_v1), and three worked cases."""
    summary = json.loads((ROUTER / "summary.json").read_text(encoding="utf-8"))
    fields = ("threshold", "coverage", "false_delegation_rate", "false_keep_rate", "false_delegations",
              "false_keeps", "delegable", "scored")
    operating = {f: summary["router_at_operating_threshold"][f] for f in fields}
    return {
        "source": "eval/benchmarks/delegation_router_v1/summary.json",
        "model": summary["model"],
        "fixture": summary["fixture"],
        "operating": operating,
        "by_threshold": [{f: entry[f] for f in fields} for entry in summary["router_by_threshold"]],
        "examples": _router_examples(operating),
    }


def _everyone() -> dict[str, Any]:
    """
    The everyone-votes reference point: every arrangement with everyone
    voting, the declared contrasts and the cap counts. Descriptive; no verdict.
    """
    manifest = json.loads((EVERYONE / "manifest.json").read_text(encoding="utf-8"))
    measures = {r["arrangement"]: r for r in _rows(EVERYONE / "measures.csv")}
    missing = [name for name in ARRANGEMENTS if name not in measures]
    if missing:
        raise ValueError(f"the everyone-votes measures.csv has no {', '.join(missing)}")
    intervals = ("fidelity_lower", "fidelity_upper", "overhead_lower", "overhead_upper")
    return {
        "source": "eval/benchmarks/delegation_everyone_votes_v1 (measures, contrasts and cap CSVs)",
        "commit": manifest["commit"],
        "declared": manifest["declared"],
        "cities": manifest["primary_cities"],
        "setting": manifest["setting"],
        "measures": {
            name: {
                **{f: float(measures[name][f]) for f in FIELDS},
                **{f: _optional(measures[name][f]) for f in EXTRA_FIELDS},
                **{f: float(measures[name][f]) for f in intervals},
            }
            for name in ARRANGEMENTS
        },
        "contrasts": {
            r["quantity"]: {f: float(r[f]) for f in ("estimate", "lower", "upper")}
            for r in _rows(EVERYONE / "contrasts.csv")
        },
        "cap": {
            r["arrangement"]: {
                "cities": int(r["cities"]),
                "meets_cap": int(r["meets_cap"]),
                "history_feasible": int(r["history_feasible"]),
            }
            for r in _rows(EVERYONE / "cap.csv")
        },
    }


def _fallback(grid: list[float]) -> dict[str, Any]:
    """
    The fallback study: liquid with the representative as default, its
    declared hypothesis read, and the default's effect at every level.
    """
    manifest = json.loads((FALLBACK / "manifest.json").read_text(encoding="utf-8"))
    hypothesis = json.loads((FALLBACK / "hypothesis.json").read_text(encoding="utf-8"))
    measures = {(r["level"], r["arrangement"]): r for r in _rows(FALLBACK / "measures.csv")}
    levels = {r["level"]: r for r in _rows(FALLBACK / "levels.csv")}

    def interval(row: dict[str, str], name: str) -> dict[str, float]:
        return {f: float(row[f"{name}_{f}"]) for f in ("estimate", "lower", "upper")}

    return {
        "source": "eval/benchmarks/delegation_fallback_v1 (measures, levels and hypothesis)",
        "commit": manifest["commit"],
        "declared": manifest["declared"],
        "cities": manifest["primary_cities"],
        "hypothesis": hypothesis["hypothesis"],
        "outcome": hypothesis["outcome"],
        "hypothesis_levels": [level["level"] for level in hypothesis["levels"]],
        "levels": {
            repr(level): {
                "liquid_default": {
                    f: _optional(measures[(repr(level), "liquid_default")][f]) for f in FALLBACK_FIELDS
                },
                "h1": interval(levels[repr(level)], "h1"),
                "cap_share": float(levels[repr(level)]["cap_share"]),
                "default_gain": interval(levels[repr(level)], "default_gain"),
                "verdict": levels[repr(level)]["frozen_verdict"],
            }
            for level in grid
        },
    }


def _exploratory(grid: list[float], frozen: dict[str, Any]) -> dict[str, Any]:
    """
    The analyses made after the freeze (§12) and one proposal's arithmetic
    (§13). Nothing here changes a frozen reading.
    """
    manifest = json.loads((HANDOVER / "manifest.json").read_text(encoding="utf-8"))
    curve = _rows(HANDOVER / "curve.csv")
    wrong = _rows(HANDOVER / "wrong_ballot.csv")
    shares = ("fidelity", "overhead", "contrary_share", "none_share")

    def bars(level: float) -> dict[str, float]:
        at = frozen[repr(level)]
        rep, liquid = at["representative"], at["liquid"]
        # How often a ballot matches its voter when one is cast: a personal
        # agent filling empty ballots must match more often to beat it
        delegated_cast = 1 - liquid["lost_share"] / liquid["delegated_share"]
        return {
            "representative": rep["fidelity"] / (1 - rep["none_share"]),
            "delegate": liquid["fidelity_resolved"] / delegated_cast,
        }

    return {
        "label": "exploratory",
        "handover": {
            "source": "eval/benchmarks/delegation_handover_v1/curve.csv",
            "commit": manifest["commit"],
            "declared": manifest["declared"],
            "cities": manifest["primary_cities"],
            "levels": {
                repr(level): [
                    {"depth": int(r["depth"]), **{f: float(r[f]) for f in shares}}
                    for r in curve
                    if float(r["level"]) == level
                ]
                for level in grid
            },
        },
        "wrong_ballot": {
            "source": "eval/benchmarks/delegation_handover_v1/wrong_ballot.csv",
            "levels": {
                repr(level): {
                    r["arrangement"]: {
                        "match": float(r["match"]),
                        "contrary": float(r["contrary"]),
                        "none": float(r["none"]),
                        "w0": float(r["score_w0"]),
                        "w1": float(r["score_w1"]),
                    }
                    for r in wrong
                    if float(r["level"]) == level
                }
                for level in grid
            },
        },
        "everyone_votes": _everyone(),
        "fallback": _fallback(grid),
        "agent_bars": {
            "label": "proposal",
            "formula": {
                "representative": "representative fidelity / (1 - representative no-ballot share)",
                "delegate": "liquid fidelity on delegated pairs / (1 - lost share / delegated share)",
            },
            "levels": {repr(level): bars(level) for level in grid},
        },
    }


def build_artifacts() -> dict[str, Any]:
    protocol = json.loads((FRONTIER / "manifest.json").read_text(encoding="utf-8"))["primary"]
    rows = [r for r in _rows(FRONTIER / "measures.csv") if r["point"] == PRIMARY]
    threshold = next(r for r in _rows(FRONTIER / "thresholds.csv") if r["point"] == PRIMARY)
    grid = protocol["protocol"]["turnout_grid"]
    levels: dict[str, dict[str, dict[str, float | None]]] = {}
    for level in grid:
        at = {r["arrangement"]: r for r in rows if float(r["level"]) == level}
        missing = [name for name in ARRANGEMENTS if name not in at]
        if missing:
            raise ValueError(f"measures.csv has no {', '.join(missing)} at {level}")
        levels[repr(level)] = {
            name: {
                **{f: float(at[name][f]) for f in FIELDS},
                **{f: _optional(at[name][f]) for f in EXTRA_FIELDS},
            }
            for name in ARRANGEMENTS
        }
    return {
        "measures.json": {
            "source": "eval/benchmarks/delegation_frontier_v1/measures.csv (primary settings)",
            "label": "frozen",
            "protocol": {
                "frozen": protocol["protocol"]["frozen"],
                "commit": protocol["commit"],
                "cities": protocol["protocol"]["primary_cities"],
                "cap": protocol["protocol"]["cap"],
                "swiss_marker": protocol["protocol"]["swiss_marker"],
                "turnout_grid": grid,
            },
            # The pre-registered verdict, word for word, and where the fidelity
            # curves cross (thresholds.csv)
            "verdict": {
                "text": threshold["verdict"],
                "crossing": float(threshold["all_cities_interpolated"]),
                "confidence": [float(threshold["confidence_low"]), float(threshold["confidence_high"])],
                "gate_holds": threshold["gate_holds"] == "true",
            },
            "levels": levels,
        },
        "results.json": {
            **_results(grid, protocol, threshold),
            "sweeps": _sweeps(grid),
            "router": _router(),
        },
        "exploratory.json": _exploratory(grid, levels),
    }


def dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest(outputs: dict[str, bytes]) -> dict[str, Any]:
    return {
        "artifact_version": ARTIFACT_VERSION,
        "generator": "scripts/build_liquid_story.py",
        "inputs": {
            **{
                f"eval/benchmarks/delegation_frontier_v1/{name}": sha256((FRONTIER / name).read_bytes())
                for name in INPUTS
            },
            "eval/benchmarks/delegation_router_v1/summary.json": sha256((ROUTER / "summary.json").read_bytes()),
            "eval/benchmarks/delegation_router_v1/judgments.jsonl": sha256((ROUTER / "judgments.jsonl").read_bytes()),
            "eval/fixtures/delegation_router_v1.json": sha256(ROUTER_FIXTURE.read_bytes()),
            **{
                f"eval/benchmarks/delegation_handover_v1/{name}": sha256((HANDOVER / name).read_bytes())
                for name in HANDOVER_INPUTS
            },
            **{
                f"eval/benchmarks/delegation_everyone_votes_v1/{name}": sha256((EVERYONE / name).read_bytes())
                for name in EVERYONE_INPUTS
            },
            **{
                f"eval/benchmarks/delegation_fallback_v1/{name}": sha256((FALLBACK / name).read_bytes())
                for name in FALLBACK_INPUTS
            },
        },
        "outputs": {name: sha256(body) for name, body in outputs.items()},
        # Written by scripts/build_liquid_example_city.py, which recomputes
        # it with the frozen code; pinned here
        "city": {"city.json": sha256(CITY.read_bytes())},
    }


def main() -> int:
    if not CITY.exists():
        print(f"{CITY} is missing: run scripts/build_liquid_example_city.py first")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    outputs = {name: dumps(payload).encode("utf-8") for name, payload in build_artifacts().items()}
    for name, body in outputs.items():
        # Bytes, not text mode: Windows text mode would write CRLF
        (OUT / name).write_bytes(body)
        print(f"{name}: {len(body) / 1024:.1f} KB")
    (OUT / "manifest.json").write_bytes(dumps(manifest(outputs)).encode("utf-8"))
    print("manifest.json written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
