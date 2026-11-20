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
- manifest.json  SHA-256 of every input and output, city.json included

Every number the page quotes is read from these files, never typed into the
page. Deterministic: the same inputs give byte-identical outputs.

Usage:
    python scripts/build_liquid_story.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Final

ROOT: Final = Path(__file__).resolve().parents[1]
FRONTIER: Final = ROOT / "eval" / "benchmarks" / "delegation_frontier_v1"
OUT: Final = ROOT / "public" / "data" / "liquid-story"
CITY: Final = OUT / "city.json"
ARTIFACT_VERSION: Final = 1
PRIMARY: Final = "primary: primary settings"
# The page's arrangements, in its order
ARRANGEMENTS: Final = ("full_turnout", "direct", "representative", "proxy", "liquid")
FIELDS: Final = ("fidelity", "contrary_share", "none_share", "overhead")
INPUTS: Final = ("measures.csv", "thresholds.csv", "manifest.json")


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build_artifacts() -> dict[str, Any]:
    protocol = json.loads((FRONTIER / "manifest.json").read_text(encoding="utf-8"))["primary"]
    rows = [r for r in _rows(FRONTIER / "measures.csv") if r["point"] == PRIMARY]
    threshold = next(r for r in _rows(FRONTIER / "thresholds.csv") if r["point"] == PRIMARY)
    grid = protocol["protocol"]["turnout_grid"]
    levels: dict[str, dict[str, dict[str, float]]] = {}
    for level in grid:
        at = {r["arrangement"]: r for r in rows if float(r["level"]) == level}
        missing = [name for name in ARRANGEMENTS if name not in at]
        if missing:
            raise ValueError(f"measures.csv has no {', '.join(missing)} at {level}")
        levels[repr(level)] = {name: {f: float(at[name][f]) for f in FIELDS} for name in ARRANGEMENTS}
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
            f"eval/benchmarks/delegation_frontier_v1/{name}": sha256((FRONTIER / name).read_bytes())
            for name in INPUTS
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
