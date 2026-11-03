"""Record the block pipeline's independent validation of Michigan's saved K13 plan.

The walkthrough's last chapter reports what was checked after the solve. This
runs the pipeline's own read-only acceptance validator
(scripts/final_state_plan_validation.py in the checkout that ran the plans)
against the saved report and writes its findings, with the validator's and
report's SHA-256, for the explainer build to cross-check. The validator
re-adds populations from the Census source file, reconciles every saved
assignment, and checks the exported district polygons; it never solves,
repairs or rewrites the plan.

Usage: python scripts/record_michigan_validation.py --cache-root <BLOCK_PLAN_CACHE_ROOT> --pipeline-root <checkout that ran the plans>
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "districting-explainer" / "michigan-validation.json"
RUN = Path("state-block-benchmark/suite-through-1000/states/26/districts-13")
VALIDATOR = Path("scripts/final_state_plan_validation.py")
KEPT = ("status", "state_fips", "district_count", "report_sha256", "checkpoint_sha256", "map_manifest_sha256",
        "source_archive_sha256", "block_count", "total_population", "district_populations", "district_block_counts",
        "max_absolute_deviation_people", "physical_polygon_components", "policy_components", "policy",
        "recorded_link_count", "checks", "limitations")


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--pipeline-root", type=Path, required=True)
    args = parser.parse_args()
    cache, pipeline = args.cache_root.resolve(), args.pipeline_root.resolve()

    sys.path.insert(0, str(pipeline))
    from scripts.final_state_plan_validation import validate_plan  # noqa: E402

    report = cache / RUN / "benchmark.json"
    result = validate_plan(report, expected_state_fips="26", expected_district_count=13)
    if result["status"] != "validated_saved_plan":
        raise SystemExit(f"Validation did not pass: {result['status']}")
    benchmark = json.loads(report.read_text("utf-8"))
    record = {
        "schemaVersion": 1,
        "validator": {"path": str(VALIDATOR).replace("\\", "/"), "sha256": sha256_file(pipeline / VALIDATOR)},
        "report": {"path": str(RUN / "benchmark.json").replace("\\", "/"), "sha256": sha256_file(report)},
        "result": {key: result[key] for key in KEPT},
        # The counts the source was checked against, as the run recorded them.
        "officialTotals": {
            "blockCount": benchmark["input"]["expected_totals"]["block_count"],
            "residentPopulation": benchmark["input"]["expected_totals"]["resident_population"],
            "blockCountSourceUrl": benchmark["input"]["block_count_source_url"],
            "residentPopulationSourceUrl": benchmark["input"]["resident_population_source_url"],
            "validated": benchmark["input"]["official_totals_validated"],
        },
        "geometry": {key: benchmark["maps"]["quality"][key] for key in (
            "source_invalid_geometries", "dissolved_geometries_valid", "district_coverage_is_valid",
            "district_overlap_area_square_meters", "source_area_sum_minus_union_square_meters")},
        "strictValidation": benchmark["maps"]["strict_validation"],
        "tractsSplit": benchmark["final_plan"]["tracts_split_across_districts"],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    print(f"Validated Michigan K13 ({result['block_count']:,} blocks); wrote {OUTPUT}")


if __name__ == "__main__":
    main()
