#!/usr/bin/env python3
"""Build the static data artifacts for the voting-methods instrument.

Runs the exhaustive paradox search in voting/search over three candidates
and writes JSON to public/data/methods/:

- specimens.json  one search record per method and criterion: the smallest
                  specimen found, certified against the reference methods,
                  or none up to the search's voter bound
- presets.json    the instrument's presets as voter types with utilities: the
                  opening majority cycle (rankings found by search, utilities
                  evenly spaced) and the center squeeze (utilities authored),
                  each with its full resolution exactly as
                  POST /api/voting/profile/resolve returns it, so the
                  instrument renders presets without the API
- manifest.json   a hash of the source that produced the outputs (the voting
                  package and the API's profile-resolution service) and output
                  SHA-256 hashes

Deterministic: the same voting package produces byte-identical outputs.
Searches run in parallel, one process per method and criterion.

Usage:
    python scripts/build_methods_artifacts.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from voting.ballot_models import evenly_spaced  # noqa: E402
from voting.search import (  # noqa: E402
    CRITERIA,
    DEFAULT_CANDIDATES,
    RANKED_METHODS,
    Criterion,
    RankedMethod,
    certify,
    find_disagreement_cycle,
    search,
    specimen_to_json,
)
from voting.types import DEFAULT_TIEBREAK_SEED  # noqa: E402
from api.schemas.voting import (  # noqa: E402
    ProfileResolveRequest,
    UtilityProfileSchema,
    UtilityRowSchema,
)
from api.services.profile_resolution import resolve_profile_request  # noqa: E402

OUT = ROOT / "public" / "data" / "methods"
ARTIFACT_VERSION = 1

# Largest electorate each search covers. Cross-profile searches visit many
# profiles per electorate, so their bounds are lower.
MAX_VOTERS: dict[Criterion, int] = {
    "majority": 24,
    "condorcet_winner": 24,
    "condorcet_loser": 24,
    "monotonicity": 24,
    "participation": 20,
    "consistency": 24,
    "iia": 24,
    "clones": 24,
}
PRESET_MAX_VOTERS = 24

# Each worker holds a search cache and, for consistency, a winner table
MAX_WORKERS = min(8, os.cpu_count() or 1)

# The center squeeze as voter types: A and B voters rate C a close-ish second,
# and C voters lean toward B. Rankings: 35 A>C>B, 33 B>C>A, 32 C>B>A.
CENTER_SQUEEZE = [
    (35, {"A": 100, "B": 0, "C": 60}),
    (33, {"A": 0, "B": 100, "C": 60}),
    (32, {"A": 0, "B": 40, "C": 100}),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "specimens.json": build_specimens(),
        "presets.json": build_presets(),
    }
    outputs: dict[str, str] = {}
    for name, payload in artifacts.items():
        body = dumps(payload).encode("utf-8")
        # Bytes, not text mode: Windows text mode would write CRLF and the
        # files would no longer match their manifest hashes.
        (OUT / name).write_bytes(body)
        outputs[name] = sha256(body)
        print(f"{name}: {len(body) / 1024:.1f} KB")

    manifest = {
        "artifact_version": ARTIFACT_VERSION,
        "generator": "scripts/build_methods_artifacts.py",
        "source_sha256": source_sha256(),
        "outputs": outputs,
    }
    (OUT / "manifest.json").write_bytes(dumps(manifest).encode("utf-8"))
    print("manifest.json written")
    return 0


def build_specimens() -> dict[str, Any]:
    cells = [(criterion, method) for criterion in CRITERIA for method in RANKED_METHODS]
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        records = list(pool.map(_search_cell, cells))
    return {
        "artifact_version": ARTIFACT_VERSION,
        "candidates": list(DEFAULT_CANDIDATES),
        "engine": "exhaustive",
        "searches": records,
    }


def _search_cell(cell: tuple[Criterion, RankedMethod]) -> dict[str, Any]:
    criterion, method = cell
    result = search(method, criterion, MAX_VOTERS[criterion])
    record: dict[str, Any] = {
        "method": method,
        "criterion": criterion,
        "max_voters": result.max_voters,
        "specimen": None,
    }
    if result.specimen is not None:
        certify(result.specimen)
        record["specimen"] = specimen_to_json(result.specimen)
    status = f"{result.specimen.voters} voters" if result.specimen else "none"
    print(f"  {criterion} / {method}: {status}", flush=True)
    return record


def build_presets() -> dict[str, Any]:
    cycle = find_disagreement_cycle(PRESET_MAX_VOTERS)
    if cycle is None:
        raise SystemExit(f"No disagreement cycle up to {PRESET_MAX_VOTERS} voters")
    cycle_rows = [
        (count, evenly_spaced(cycle.candidates, ranking)) for count, ranking in cycle.rows
    ]
    return {
        "artifact_version": ARTIFACT_VERSION,
        "presets": [
            {
                "id": "majority-cycle",
                "found_by": {"search": "disagreement_cycle", "max_voters": PRESET_MAX_VOTERS},
                "utilities": "evenly spaced",
                "resolution": preset_resolution(list(cycle.candidates), cycle_rows),
            },
            {
                "id": "center-squeeze",
                "found_by": None,
                "utilities": "authored",
                "resolution": preset_resolution(list(DEFAULT_CANDIDATES), CENTER_SQUEEZE),
            },
        ],
    }


def preset_resolution(
    candidates: list[str], rows: list[tuple[int, dict[str, int]]]
) -> dict[str, Any]:
    """The endpoint's response for a preset; every method must be decisive."""
    request = ProfileResolveRequest(
        profile=UtilityProfileSchema(
            ballot_type="utility",
            candidates=candidates,
            rows=[UtilityRowSchema(count=count, utilities=u) for count, u in rows],
        ),
        tiebreak_seed=DEFAULT_TIEBREAK_SEED,
    )
    response = resolve_profile_request(request)
    for result in response.results:
        if not result.decisive:
            raise SystemExit(f"Preset needs a tiebreak under {result.method}")
    return response.model_dump(mode="json")


# Source files whose behavior the outputs depend on, besides voting/
RESOLUTION_SOURCES = ("api/schemas/voting.py", "api/services/profile_resolution.py")


def source_sha256() -> str:
    """
    Hash of the source that produced the outputs: the voting package (tests
    excluded) and the API's profile-resolution modules, line endings normalized.
    """
    digest = hashlib.sha256()
    paths = [p for p in (ROOT / "voting").rglob("*.py") if "tests" not in p.parts]
    paths += [ROOT / name for name in RESOLUTION_SOURCES]
    for path in sorted(paths, key=lambda p: p.relative_to(ROOT).as_posix()):
        relative = path.relative_to(ROOT).as_posix()
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


def dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=False) + "\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


if __name__ == "__main__":
    sys.exit(main())
