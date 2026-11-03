# Kansas shared-edge connectivity benchmark — October 22, 2026

The Kansas census-block plan now has four shared-edge-connected districts with
**734,470 people each**, exactly the target population. The complete offline
pipeline took **301.74 seconds (5 min 02 s)** and peaked at **573.86 MiB** of
Python process working set. This is a separate benchmark artifact; the main
demo's saved tract maps have not been replaced.

Machine-readable measurements: [kansas-connectivity-benchmark.json](kansas-connectivity-benchmark.json).
Comparison baseline: [original block benchmark](kansas-block-benchmark.md).

## Same input and initial plan

The run includes all **172,529 Kansas blocks**, including **63,380 zero-population
blocks** and **3,210 water-only blocks**, from the official 2020 TIGER/Line archive.
Their published populations total **2,937,880**. Every block remains whole;
tracts may be split. The final plan splits 61 of 829 tracts, versus 60 originally.

The archive hash, seed `20200955`, four-district count, and numerical solver
settings match the original experiment. The runner checks that the complete
initial assignment mapping is identical to the saved baseline. It passed.
The numerical solver is unchanged; its documentation now distinguishes
continuous convex power cells from unions of whole Census polygons.

## Connectivity rule and correction

Two blocks are neighbors only if their interiors are disjoint and their
boundaries share a line segment of positive length (`F***1****` in DE-9IM).
The graph uses original source coordinates without rounding, snapping, or
buffering. Corner-only contacts do not count. Water blocks do count, and no
minimum shared-edge length or corridor width is imposed.

The graph contains **408,475 undirected edges**, excludes **202,624 corner-only
pairs**, and forms one connected statewide component with no isolated blocks.
All source geometries are valid single polygons; no interior overlaps were
found among spatial-index candidates.

Repair retains each district's largest-population component and transfers
detached components to adjacent connected district territory. Deterministic
ties and population balance choose among eligible transfers. Rebalancing then
considers single populated boundary-block transfers, accepting a move only if
it improves maximum deviation, or squared error at the same maximum, and keeps
both districts connected. The recipient must share an edge; a donor graph
check rejects any move that would disconnect its remaining blocks.

| Stage | District populations | Shared-edge components | Worst deviation | Population range |
|---|---|---|---:|---:|
| Initial power assignment | 734,523 / 734,458 / 734,537 / 734,362 | 3 / 5 / 3 / 11 | 108 (0.01470%) | 175 |
| After connectivity repair | 734,523 / 734,701 / 734,537 / 734,119 | 1 / 1 / 1 / 1 | 351 (0.04779%) | 582 |
| After rebalancing | 734,470 / 734,470 / 734,470 / 734,470 | 1 / 1 / 1 / 1 | **0 (0%)** | **0** |

Repair made 18 component transfers involving 19 blocks and 255 residents.
Nine subsequent boundary-block transfers involved another 420 residents.
Overall, **28 blocks carrying 675 residents** changed district. The move log
records block GEOIDs, source and destination districts, and population for
every transfer.

An independent graph traversal validates each stage. Final dissolved polygons
also have exactly one component per district, are valid, cover all supplied
source blocks, and have zero measured inter-district overlap. Population totals
reconcile independently during map export. Display simplification preserves
shared boundaries and does not change assignments or population.

This exact balance is a result for this Kansas run, not a general promise for
other states or district counts. The search stops at a single-block local
optimum and does not explore swaps or neutral moves. Corrected boundaries are
no longer an exact power diagram; compactness is not an acceptance constraint
in this repair experiment.

## Runtime and memory

Both observations used the same desktop: Windows 10, Ryzen 7 3700X, roughly
16 GiB RAM, Python 3.11.3, NumPy 2.4.4, SciPy 1.17.1, pyshp 3.0.3, and
Shapely 2.1.2. Each is one local run, not a repeated controlled performance
study. The source archive was cached; the new graph was built from scratch.

| Phase | Original | Connected and rebalanced |
|---|---:|---:|
| Validate archive, extract, read records | 2.94 s | 3.70 s |
| Original numerical solver | 20.81 s | 23.94 s |
| Build shared-edge graph | — | 45.81 s |
| Repair and rebalance | — | 2.39 s |
| Independent graph audits | — | 0.82 s |
| Validate and export all map artifacts | 197.91 s | 224.60 s |
| **Complete timed pipeline** | **222.07 s** | **301.74 s** |
| **Peak Python process working set** | **532.92 MiB** | **573.86 MiB** |

The observed total increased by **79.67 s (35.9%)**. Newly added graph building,
correction, and graph audits account for 49.01 s. The unchanged solver and
exporter also ran slower in this observation; the entire difference should
not be attributed to contiguity enforcement. Peak working set increased by
40.94 MiB (7.7%). The operating system supplies the overall high-water mark;
per-phase memory is sampled every 100 ms. Browser memory is excluded.

The shared-edge graph depends on source geometry, not on the number of
districts. Caching it once per state/source hash would amortize its construction
across future district counts. No graph cache is used in these measurements.

## Map loading

These are actual gzip file sizes, excluding the viewer shell and HTTP headers.
They describe transfer payloads, not browser memory or deployed latency.

| Request | Original gzip | Corrected gzip |
|---|---:|---:|
| Kansas outlines for national view | 14,725 B (14.4 KiB) | **13,706 B (13.4 KiB)** |
| State outlines plus county index | 84,359 B (82.4 KiB) | **81,219 B (79.3 KiB)** |
| Exact unsimplified district outlines | 308,811 B | **298,040 B (291.1 KiB)** |
| All 105 county block files | 52,714,255 B | **52,714,254 B (50.3 MiB)** |
| Largest county, Johnson | 2,106,561 B | **2,106,559 B (2.01 MiB)** |
| Sedgwick, 12,158 blocks | 2,055,190 B | **2,055,190 B (1.96 MiB)** |

The national view still needs only district outlines. Opening Kansas loads
state outlines and the county index; full block geometry loads by county on
request. State and national display simplification settings are unchanged
from the baseline. Source block coordinates are retained in county files.

The standalone viewer at `http://127.0.0.1:8768/` uses the corrected output.
Browser verification confirmed national/state rendering, gzip transfer sizes,
district population inspection, and on-demand county detail.

## Reproduce and inspect

From the repository root in PowerShell:

```powershell
.\venv\Scripts\python.exe scripts/benchmark_kansas_connectivity.py
.\venv\Scripts\python.exe scripts/serve_district_benchmark.py --directory .cache/kansas-block-benchmark/run-435-connected --port 8768
```

The runner saves the report, all assignments, a move audit, and map artifacts
in `.cache/kansas-block-benchmark/run-435-connected/`. It preserves the original
`run-435` output. `--output` selects another directory; `--skip-export` runs
the graph stages without map export. The viewer HTML is a local inspection
artifact copied from the original experiment, not generated by the runner.

Source and implementation SHA-256 hashes, package versions, detailed phase
timings, graph statistics, geometry diagnostics, and all county sizes are in
the JSON report. The report's source hash is
`a0ccda5300d1994008b51bf345c77bc1b04adc8df6219b226c64b80d3a611198`.

Validation: **94 tests passed** across districting and shared-edge construction,
including corner contacts, gaps, tiny edges, articulation points, move replay,
and determinism. The new pure graph module passes strict mypy. No commit was
created.
