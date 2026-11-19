"""
Demo 5's published benchmark: the frozen primary and sweep runs of the
liquid-democracy comparison, packaged so that every verdict can be checked
without rerunning the six hours of simulation.

  python -m eval.delegation_frontier publish
      Package the recorded runs (.cache/liquid-benchmark/{primary,sweeps})
      into eval/benchmarks/delegation_frontier_v1/: every recorded city,
      both reports exactly as the runner wrote them (gzipped, like the
      cities), the two run manifests,
      and CSV summaries derived from them. Refuses a run that is not from
      the freeze's merge commit, clean, complete and analysed on its own
      code.
  python -m eval.delegation_frontier rebuild
      Rewrite the summaries and metadata.json from the published files alone.
  python -m eval.delegation_frontier verify
      Check every published hash, rebuild the summaries, and re-read every
      verdict from the published cities with the current runner and
      protocol. Any difference from the published files is an error.

The city records (about 7 MB) are kept out of the repository: the
benchmark's .gitignore excludes them, and metadata.json keeps their hashes.
Without them, verify checks every committed file's hash and the runs'
provenance; `publish` from the recorded runs regenerates them byte for byte,
after which verify re-derives the summaries and every verdict as well.

Figures: python -m eval.plot_delegation_frontier.
Design: prompts/demo-5-liquid-democracy.md, "Running the benchmark".

Nothing here simulates a city or changes a reading. The summaries are the
reports' own numbers, flattened, plus one derived quantity the reports do
not store: the simultaneous band itself (the reports store its critical
value). The band is recomputed with the protocol's own curve and band
arithmetic, and checked against the confidence set the report recorded.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import numpy as np
import numpy.typing as npt

from delegation.comparison import protocol, runner
from delegation.comparison.sweeps import FRONTIER_FLOORS, PRIMARY_POINT, SWEEP_CITIES, SWEEPS

ROOT: Final = Path(__file__).resolve().parents[1]
BENCHMARK_ID: Final = "delegation_frontier_v1"
DEFAULT_RUNS: Final = ROOT / ".cache" / "liquid-benchmark"
DEFAULT_OUT: Final = ROOT / "eval" / "benchmarks" / BENCHMARK_ID
# The merge commit of the freeze PR; both runs come from it
FREEZE_COMMIT: Final = "a50ebcc51ca6df466881db610ea0693f9b48b4d1"
MODES: Final = ("primary", "sweeps")

PRIMARY_KEY: Final = runner.point_key(PRIMARY_POINT)
REFERENCE_KEY: Final = runner.REFERENCE_KEY
STRUCTURAL_BASELINE: Final = runner._structural_baseline_key()

# Recorded inputs, copied from the runs. The city records stay out of the
# repository (see the module docstring); the reports and manifests are in it
CITIES: Final = {mode: f"{mode}_cities.jsonl.gz" for mode in MODES}
REPORTS: Final = {mode: f"{mode}_report.json.gz" for mode in MODES}
MANIFEST: Final = "manifest.json"
# Derived from them
SUMMARIES: Final = ("thresholds.csv", "levels.csv", "frontier.csv", "decomposition.csv", "measures.csv")
METADATA: Final = "metadata.json"
SOURCE: Final = "eval/delegation_frontier.py"


class PublishError(ValueError):
    """A run, or a published file, that cannot be published or verified as is."""


# ---------------------------------------------------------------------------
# Reading the recorded runs
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _city_lines(run: Path) -> list[bytes]:
    """
    Every recorded city of a run as its exact recorded bytes, in (point,
    position) order. Each file is one line of compact JSON as the runner
    wrote it, so a line can be put back as the file it came from.
    """
    lines: list[tuple[tuple[str, int], bytes]] = []
    for path in (run / runner.CITIES).glob("*/*.json"):
        data = path.read_bytes()
        if b"\n" in data or b"\r" in data:
            raise PublishError(f"{path} is not one line of JSON")
        row = json.loads(data)
        if path != runner.city_path(run, row["point"], int(row["position"])):
            raise PublishError(f"{path} does not hold the city its name says")
        lines.append(((row["point"], int(row["position"])), data))
    return [data for _, data in sorted(lines)]


def _check_run(
    mode: str, manifest: Mapping[str, Any], report: Mapping[str, Any], rows: Sequence[Any] | None
) -> None:
    """
    A run is publishable only as the frozen, complete, self-analysed run.
    Without its city records (`rows` None) the cities themselves are not
    counted; everything the manifest and report say is still checked.
    """
    expected = {
        "mode": mode,
        "commit": FREEZE_COMMIT,
        "dirty": False,
        "diff_sha256": None,
        "runner_version": runner.RUNNER_VERSION,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise PublishError(f"the {mode} run has {key} {manifest.get(key)!r}, not {value!r}")
    if manifest["protocol"]["frozen"] != protocol.PROTOCOL_FROZEN:
        raise PublishError(f"the {mode} run was not made under the frozen protocol")
    if report.get("manifest") != manifest:
        raise PublishError(f"the {mode} report was not written for this run's manifest")
    if report.get("mode") != mode or report.get("reanalysis") is not False:
        raise PublishError(f"the {mode} report is not the run's own analysis")
    if report.get("missing_points"):
        raise PublishError(f"the {mode} run is missing {report['missing_points']}")
    incomplete = [key for key, point in report["points"].items() if not point.get("complete")]
    if incomplete:
        raise PublishError(f"the {mode} run has incomplete points: {incomplete}")
    if rows is not None:
        declared = runner.validate(rows, mode)
        if len(rows) != len(declared):
            raise PublishError(f"the {mode} run has {len(rows)} of {len(declared)} declared cities")
    if mode == "sweeps" and report.get("reference", {}).get("status") != "ok":
        raise PublishError("the sweeps report has no fitted reference")


def _gzip(data: bytes) -> bytes:
    # mtime 0 and no file name: the same lines always give the same bytes
    return gzip.compress(data, compresslevel=9, mtime=0)


def publish(runs: Path, out: Path) -> list[Path]:
    """Copy the frozen runs into `out`, then build the summaries and metadata."""
    manifests: dict[str, Any] = {}
    for mode in MODES:
        run = runs / mode
        manifest = _read_json(run / runner.MANIFEST)
        report_bytes = (run / "report.json").read_bytes()
        report = json.loads(report_bytes)
        lines = _city_lines(run)
        _check_run(mode, manifest, report, [json.loads(line) for line in lines])
        manifests[mode] = manifest
        out.mkdir(parents=True, exist_ok=True)
        (out / CITIES[mode]).write_bytes(_gzip(b"".join(line + b"\n" for line in lines)))
        (out / REPORTS[mode]).write_bytes(_gzip(report_bytes))
    shared = ("commit", "dirty", "diff_sha256", "beliefs_sha256", "protocol", "python", "numpy", "scipy")
    for key in shared:
        if manifests["primary"].get(key) != manifests["sweeps"].get(key):
            raise PublishError(f"the primary and sweep runs differ in {key}")
    (out / MANIFEST).write_text(_dumps(manifests) + "\n", encoding="utf-8", newline="\n")
    return [out / CITIES[m] for m in MODES] + [out / REPORTS[m] for m in MODES] + rebuild(out)


# ---------------------------------------------------------------------------
# The published files
# ---------------------------------------------------------------------------


def _dumps(value: Any) -> str:
    return runner._dumps(value, indent=2, sort_keys=True)


def load_cities(directory: Path, mode: str) -> list[dict[str, Any]]:
    data = gzip.decompress((directory / CITIES[mode]).read_bytes())
    return [json.loads(line) for line in data.splitlines()]


def load_report(directory: Path, mode: str) -> dict[str, Any]:
    report: dict[str, Any] = json.loads(gzip.decompress((directory / REPORTS[mode]).read_bytes()))
    return report


def point_order(sweeps_report: Mapping[str, Any]) -> list[str]:
    """Primary, the fitted reference, then the sweep points in declared order."""
    declared = [runner.point_key(p) for p in SWEEPS]
    if set(declared) != set(sweeps_report["points"]):
        raise PublishError("the sweeps report does not hold exactly the declared points")
    return [PRIMARY_KEY, REFERENCE_KEY, *declared]


def readings(directory: Path) -> dict[str, dict[str, Any]]:
    """Every point's reading, keyed as in point_order."""
    primary, sweeps = load_report(directory, "primary"), load_report(directory, "sweeps")
    out = {PRIMARY_KEY: primary["points"][PRIMARY_KEY], REFERENCE_KEY: sweeps["reference"]["reading"]}
    out.update(sweeps["points"])
    return {key: out[key] for key in point_order(sweeps)}


def baselines(sweeps_report: Mapping[str, Any]) -> dict[str, tuple[str, dict[str, Any]]]:
    """
    Each sweep point's declared baseline and its paired gap to it, level by
    level: fitted points against the fitted reference, structural points
    against the structural 0.87 point, and that point against the fitted
    reference (the generator gap).
    """
    reference = sweeps_report["reference"]
    out: dict[str, tuple[str, dict[str, Any]]] = {}
    for key, gap in reference["fitted_gaps"].items():
        out[key] = (gap["baseline"], gap["by_level"])
    for key, gap in reference["structural_gaps"].items():
        out[key] = (gap["baseline"], gap["by_level"])
    generator = reference["generator_gap"]
    if STRUCTURAL_BASELINE is not None:
        out[STRUCTURAL_BASELINE] = (generator["baseline"], generator["by_level"])
    return out


# ---------------------------------------------------------------------------
# The simultaneous band, recomputed with the protocol's arithmetic
# ---------------------------------------------------------------------------


def _as_float(value: Any) -> float:
    if value == "inf":
        return math.inf
    if value == "-inf":
        return -math.inf
    return float(value)


def bands(
    rows: Sequence[Mapping[str, Any]], key: str, reading: Mapping[str, Any]
) -> dict[str, tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]]:
    """
    The simultaneous 95% band of both curves, in fidelity units, from one
    point's recorded cities and the critical value its report recorded. The
    curves, standard errors and band are protocol.threshold's own
    (`_curves`, `_band`), stratified where the point rotates its agenda; the
    confidence set the band implies must equal the one in the report.
    """
    levels = reading["levels"]
    pairs = float(reading["pairs"])
    ordered = sorted(rows, key=lambda r: int(r["position"]))
    positions = [int(r["position"]) for r in ordered]
    counts = np.array(
        [[runner._contrast(r["levels"][repr(level)], "h1") for level in levels] for r in ordered],
        dtype=np.float64,
    )
    cap = np.array([[r["levels"][repr(level)]["liquid_meets_cap"] for level in levels] for r in ordered])
    sweep = runner.POINTS.get(key)
    strata = None if sweep is None else sweep.strata(positions)
    curve_all, curve_cap = protocol._curves(counts, cap, strata)
    critical = _as_float(reading["threshold"]["band_critical"])
    out = {}
    indices = []
    for name, curve in (("all_cities", curve_all), ("cap_meeting", curve_cap)):
        lower, upper = protocol._band(curve.mean, curve.se, critical)
        indices.append(protocol._band_index(lower, upper))
        out[name] = (lower / pairs, upper / pairs)
    earliest, latest = max(i[0] for i in indices), max(i[1] for i in indices)
    n = len(levels)
    confidence = [
        -math.inf if earliest == 0 else levels[earliest - 1],
        math.inf if latest == n else levels[latest],
    ]
    recorded = [_as_float(x) for x in reading["threshold"]["confidence"]]
    if confidence != recorded:
        raise PublishError(f"{key}: the recomputed band gives {confidence}, the report {recorded}")
    return out


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------


def _num(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    number = float(value)
    if math.isinf(number):
        return "inf" if number > 0 else "-inf"
    # Six decimals, trailing zeros dropped: fidelity is a share of 80,000 or so
    # pairs, and the reports keep full precision
    text = f"{number:.6f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _interval_cells(interval: Mapping[str, Any] | None) -> list[str]:
    if interval is None:
        return ["", "", ""]
    return [_num(interval["estimate"]), _num(interval["lower"]), _num(interval["upper"])]


def _pair(value: Sequence[Any] | None) -> list[str]:
    return ["", ""] if value is None else [_num(value[0]), _num(value[1])]


def _csv(header: Sequence[str], rows: Iterable[Sequence[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        if len(row) != len(header):
            raise AssertionError("a summary row must match its header")
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def _describe(key: str) -> tuple[str, str, str]:
    if key == REFERENCE_KEY:
        return "primary", "primary settings, positions 1-48", PRIMARY_POINT.population
    point = runner.POINTS[key]
    return point.family, point.label, point.population


def summaries(directory: Path) -> dict[str, bytes]:
    """Every summary CSV, from the published reports and cities alone."""
    sweeps_report = load_report(directory, "sweeps")
    points = readings(directory)
    gaps = baselines(sweeps_report)
    cities: dict[str, list[dict[str, Any]]] = {PRIMARY_KEY: [], REFERENCE_KEY: []}
    for row in load_cities(directory, "primary"):
        cities[PRIMARY_KEY].append(row)
        if int(row["position"]) <= SWEEP_CITIES:
            cities[REFERENCE_KEY].append(row)
    for row in load_cities(directory, "sweeps"):
        cities.setdefault(row["point"], []).append(row)

    thresholds = []
    levels_rows = []
    decomposition = []
    measures = []
    frontier = []
    measure_fields: list[str] | None = None
    for key, reading in points.items():
        family, label, population = _describe(key)
        t = reading["threshold"]
        baseline, gap_levels = gaps.get(key, ("", {}))
        thresholds.append(
            [
                key,
                family,
                label,
                population,
                _num(reading["cities"]),
                t["verdict"],
                t["status"],
                *_pair(t["bracket"]),
                _num(t["interpolated"]),
                _num(t["first_supported"]),
                _num(t["all_cities"]["interpolated"]),
                *_pair(t["confidence"]),
                _num(t["gate_holds"]),
                _num(t["band_critical"]),
                ";".join(_num(x) for x in t["zero_spread_levels"]),
                baseline,
            ]
        )
        band = bands(cities[key], key, reading)
        for j, level in enumerate(reading["levels"]):
            by = reading["by_level"][repr(level)]
            h1, spec = by["h1"], by["specialisation"]
            levels_rows.append(
                [
                    key,
                    _num(level),
                    _num(by["cap_share"]),
                    _num(h1["cap_meeting_cities"]),
                    *_interval_cells(h1["all_cities"]),
                    *_interval_cells(h1["cap_meeting"]),
                    _num(band["all_cities"][0][j]),
                    _num(band["all_cities"][1][j]),
                    _num(band["cap_meeting"][0][j]) if h1["cap_meeting_cities"] else "",
                    _num(band["cap_meeting"][1][j]) if h1["cap_meeting_cities"] else "",
                    h1["direction"],
                    h1["size"],
                    *_interval_cells(spec["all_cities"]),
                    *_interval_cells(spec["both_meet_cap"]),
                    _num(spec["joint_share"]),
                    spec["direction"],
                    spec["size"],
                    baseline,
                    *_interval_cells(gap_levels.get(repr(level))),
                ]
            )
            for name, interval in by["decomposition"].items():
                decomposition.append([key, _num(level), name, *_interval_cells(interval)])
            for name, part in by["attribution"].items():
                for side in ("kept", "resolved"):
                    decomposition.append(
                        [key, _num(level), f"{name}.{side}", *_interval_cells(part[f"{side}_contribution"])]
                    )
            for arm, values in by["measures"].items():
                names = list(values)
                if measure_fields is None:
                    measure_fields = names
                elif names != measure_fields:
                    raise PublishError(f"{key} at {level}: measures differ from the first point's")
                measures.append([key, _num(level), arm, *(_num(values[n]) for n in names)])
            if key == PRIMARY_KEY:
                f = by["frontier"]
                for floor, interval in zip(FRONTIER_FLOORS, f["pointwise"], strict=True):
                    frontier.append(
                        [
                            _num(level),
                            _num(floor),
                            *_interval_cells(interval),
                            f["status"],
                            *_pair(f["bracket"]),
                            _num(f["interpolated"]),
                        ]
                    )
    if measure_fields is None:
        raise PublishError("no measures to summarise")
    interval = ("estimate", "lower", "upper")
    return {
        "thresholds.csv": _csv(
            [
                "point",
                "family",
                "label",
                "population",
                "cities",
                "verdict",
                "status",
                "bracket_low",
                "bracket_high",
                "interpolated",
                "first_supported",
                "all_cities_interpolated",
                "confidence_low",
                "confidence_high",
                "gate_holds",
                "band_critical",
                "zero_spread_levels",
                "baseline",
            ],
            thresholds,
        ),
        "levels.csv": _csv(
            [
                "point",
                "level",
                "cap_share",
                "cap_meeting_cities",
                *(f"h1_all_{x}" for x in interval),
                *(f"h1_cap_{x}" for x in interval),
                "band_all_lower",
                "band_all_upper",
                "band_cap_lower",
                "band_cap_upper",
                "h1_direction",
                "h1_size",
                *(f"specialisation_all_{x}" for x in interval),
                *(f"specialisation_matched_{x}" for x in interval),
                "specialisation_joint_share",
                "specialisation_direction",
                "specialisation_size",
                "baseline",
                *(f"gap_{x}" for x in interval),
            ],
            levels_rows,
        ),
        "frontier.csv": _csv(
            ["level", "floor", *interval, "status", "bracket_low", "bracket_high", "interpolated"],
            frontier,
        ),
        "decomposition.csv": _csv(["point", "level", "quantity", *interval], decomposition),
        "measures.csv": _csv(["point", "level", "arrangement", *measure_fields], measures),
    }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_sha256() -> str:
    return _sha256((ROOT / SOURCE).read_bytes().replace(b"\r\n", b"\n"))


def metadata(directory: Path, built: Mapping[str, bytes]) -> bytes:
    """Provenance: the runs, their environment, and every file's hash."""
    manifests = _read_json(directory / MANIFEST)
    primary = manifests["primary"]
    recorded = [CITIES[m] for m in MODES] + [REPORTS[m] for m in MODES] + [MANIFEST]
    outputs = {name: _sha256((directory / name).read_bytes()) for name in recorded}
    outputs.update({name: _sha256(data) for name, data in built.items()})
    sweeps = load_report(directory, "sweeps")["points"]
    value = {
        "benchmark_id": BENCHMARK_ID,
        "generator": "python -m eval.delegation_frontier publish",
        "freeze_commit": FREEZE_COMMIT,
        "protocol_frozen": primary["protocol"]["frozen"],
        "runner_version": primary["runner_version"],
        "beliefs_sha256": primary["beliefs_sha256"],
        "environment": {k: primary[k] for k in ("python", "numpy", "scipy")},
        "runs": {
            "primary": {"points": 1, "cities": load_report(directory, "primary")["points"][PRIMARY_KEY]["cities"]},
            "sweeps": {"points": len(sweeps), "cities": sum(p["cities"] for p in sweeps.values())},
        },
        "participant_data": False,
        "inference_provider_calls": 0,
        "source_sha256_lf_normalized": {SOURCE: _source_sha256()},
        "outputs": dict(sorted(outputs.items())),
    }
    return (_dumps(value) + "\n").encode("utf-8")


def has_cities(directory: Path) -> bool:
    """Whether both runs' city records are present (they are not committed)."""
    return all((directory / CITIES[mode]).exists() for mode in MODES)


def build(directory: Path) -> dict[str, bytes]:
    if not has_cities(directory):
        raise PublishError(
            f"the city records are not in {directory}: regenerate them with publish from the recorded runs"
        )
    built = summaries(directory)
    built[METADATA] = metadata(directory, built)
    return built


def rebuild(directory: Path) -> list[Path]:
    """Rewrite the summaries and metadata.json from the published files."""
    paths = []
    for name, data in build(directory).items():
        path = directory / name
        path.write_bytes(data)
        paths.append(path)
    return paths


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def _unpack(directory: Path, mode: str, run: Path) -> None:
    """The published cities of one run, back in the runner's directory layout."""
    manifest = _read_json(directory / MANIFEST)[mode]
    run.mkdir(parents=True)
    (run / runner.MANIFEST).write_text(runner._dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for line in gzip.decompress((directory / CITIES[mode]).read_bytes()).splitlines():
        row = json.loads(line)
        path = runner.city_path(run, row["point"], int(row["position"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(line)


def _normal(value: Any) -> Any:
    """JSON as published: NaN as null and infinities as strings."""
    return json.loads(runner._dumps(value))


def reanalyse(directory: Path) -> list[str]:
    """
    Re-read every verdict from the published cities with the current runner
    and protocol. Returns the report sections that differ from the published
    reports (empty when every reading is reproduced exactly).
    """
    differences = []
    with tempfile.TemporaryDirectory() as scratch:
        base = Path(scratch)
        for mode in MODES:
            _unpack(directory, mode, base / mode)
        for mode in MODES:
            fresh = runner.analyse(base / mode, mode, primary_out=base / "primary", allow_reanalysis=True)
            published = load_report(directory, mode)
            for section in ("points", "missing_points", "reference"):
                if section in published or section in fresh:
                    if _normal(fresh.get(section)) != published.get(section):
                        differences.append(f"{mode}: {section}")
    return differences


def verify(directory: Path, *, analyse: bool = True) -> list[str]:
    """
    Every problem with a published benchmark directory; empty when it holds.

    Without the city records, which are not committed, it checks every other
    file's hash and both runs' provenance. With them it also rebuilds the
    summaries and, with `analyse`, re-reads every verdict.
    """
    problems = []
    cities = has_cities(directory)
    recorded = _read_json(directory / METADATA)["outputs"]
    for name, digest in recorded.items():
        path = directory / name
        if not path.exists():
            if name not in CITIES.values():
                problems.append(f"{name} is missing")
        elif _sha256(path.read_bytes()) != digest:
            problems.append(f"{name} does not match its recorded hash")
    for mode in MODES:
        report = load_report(directory, mode)
        manifest = _read_json(directory / MANIFEST)[mode]
        try:
            _check_run(mode, manifest, report, load_cities(directory, mode) if cities else None)
        except PublishError as error:
            problems.append(str(error))
    if not cities:
        return problems
    for name, data in build(directory).items():
        if (directory / name).read_bytes() != data:
            problems.append(f"{name} does not rebuild byte for byte")
    if analyse:
        problems.extend(f"reanalysis differs in {section}" for section in reanalyse(directory))
    return problems


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("publish")
    cmd.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    cmd.add_argument("--out", type=Path, default=DEFAULT_OUT)
    for name in ("rebuild", "verify"):
        sub.add_parser(name).add_argument("directory", type=Path, nargs="?", default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    try:
        if args.command == "publish":
            for path in publish(args.runs, args.out):
                print(f"wrote {path}")
        elif args.command == "rebuild":
            for path in rebuild(args.directory):
                print(f"wrote {path}")
        else:
            problems = verify(args.directory)
            for problem in problems:
                print(problem)
            if problems:
                sys.exit(1)
            if has_cities(args.directory):
                print("every hash holds, the summaries rebuild, and every verdict is reproduced")
            else:
                print(
                    "every committed hash holds and both runs are the frozen runs. The city records are not "
                    "here, so the summaries and verdicts were not re-derived; regenerate the records with "
                    "publish from the recorded runs to check those too."
                )
    except PublishError as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
