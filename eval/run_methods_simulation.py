"""Run the voting-methods simulation and write its benchmark and page summary.

Writes eval/benchmarks/methods_simulation_v1/:
- config.json        the executed configuration
- elections.csv.gz   one row per election: every method's winner and
                     whether the ballots alone decided it, the Condorcet
                     winner, and how an instant-runoff tie was settled
- summary.json       Condorcet-winner existence, Condorcet efficiency, tie
                     rates and pairwise disagreement, with 95% Wilson intervals
- metadata.json      versions, the source hash, and output hashes

and public/data/methods/simulation.json, the summary the /methods page
reads. Outputs are byte-identical across runs and worker counts. Existing
evidence is not overwritten without --overwrite.

Usage:
    python -m eval.run_methods_simulation [--workers 8] [--overwrite]
"""

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import platform
from pathlib import Path
from typing import Any

import numpy as np

from .methods_simulation import (
    STUDY_ID,
    SimulationConfig,
    config_json,
    record_header,
    record_row,
    run_simulation,
    summarize,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = REPO_ROOT / "eval" / "benchmarks" / STUDY_ID
PAGE_SUMMARY = REPO_ROOT / "public" / "data" / "methods" / "simulation.json"
GENERATED = ("config.json", "elections.csv.gz", "summary.json", "metadata.json")
# Source the outputs depend on, besides voting/
STUDY_SOURCES = ("eval/methods_simulation.py", "eval/run_methods_simulation.py")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    existing = [name for name in GENERATED if (BENCHMARK / name).exists()]
    if existing and not args.overwrite:
        raise SystemExit(f"{BENCHMARK} already holds {existing}; pass --overwrite to replace them")

    config = SimulationConfig()
    records = run_simulation(config, workers=args.workers)
    summary = summarize(records, config)

    outputs = {
        "config.json": json_bytes(config_json(config)),
        "elections.csv.gz": csv_gz_bytes([record_header()] + [record_row(r) for r in records]),
        "summary.json": json_bytes(summary),
    }
    source = source_sha256()
    page = {
        **summary,
        "benchmark": f"eval/benchmarks/{STUDY_ID}",
        "source_sha256": source,
    }
    page_bytes = json_bytes(page)
    metadata = {
        "study": STUDY_ID,
        "generator": "python -m eval.run_methods_simulation",
        "python": platform.python_version(),
        "numpy": np.__version__,
        "source_sha256": source,
        "outputs": {name: sha256(body) for name, body in outputs.items()},
        "page_summary": {"path": "public/data/methods/simulation.json", "sha256": sha256(page_bytes)},
    }
    outputs["metadata.json"] = json_bytes(metadata)

    BENCHMARK.mkdir(parents=True, exist_ok=True)
    for name, body in outputs.items():
        (BENCHMARK / name).write_bytes(body)
        print(f"{name}: {len(body) / 1024:.1f} KB")
    PAGE_SUMMARY.write_bytes(page_bytes)
    print(f"{PAGE_SUMMARY.relative_to(REPO_ROOT).as_posix()}: {len(page_bytes) / 1024:.1f} KB")
    return 0


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")


def csv_gz_bytes(rows: list[list[str]]) -> bytes:
    text = io.StringIO(newline="")
    csv.writer(text, lineterminator="\n").writerows(rows)
    # mtime=0 and no file name, so the archive is byte-identical across runs
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0) as archive:
        archive.write(text.getvalue().encode("utf-8"))
    return buffer.getvalue()


def source_sha256() -> str:
    """The voting package (tests excluded) and the study's own modules, line endings normalized."""
    digest = hashlib.sha256()
    paths = [p for p in (REPO_ROOT / "voting").rglob("*.py") if "tests" not in p.parts]
    paths += [REPO_ROOT / name for name in STUDY_SOURCES]
    for path in sorted(paths, key=lambda p: p.relative_to(REPO_ROOT).as_posix()):
        digest.update(path.relative_to(REPO_ROOT).as_posix().encode("utf-8") + b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
