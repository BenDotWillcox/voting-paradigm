# Kansas census-block benchmark — October 22, 2026

Kansas at census-block resolution is practical for offline precomputation and
progressive map loading. The existing solver produced a well-balanced result
quickly, but whole-block assignment left disconnected pieces. This is a
feasibility result, not a validated contiguous district plan.

## Scope and source

- Four districts, corresponding to Kansas's allocation in a 435-seat House.
- All **172,529 blocks**, including **63,380 zero-population blocks** and
  **3,210 water-only blocks**, from the
  [official 2020 TIGER/Line Kansas block archive](https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/tl_2020_20_tabblock20.zip).
- **109,149 populated blocks**, **829 tracts**, and **2,937,880 residents**.
  Block totals match the [Census geography tallies](https://www.census.gov/geographies/reference-files/time-series/geo/tallies.2020.html).
- Geometry and `POP20` arrive together, so no external population join is needed.
  Every GEOID is unique and assigned exactly once; source, solver, and map
  population totals reconcile independently.
- The source archive is **162,837,181 bytes (155.3 MiB)**. SHA-256:
  `a0ccda5300d1994008b51bf345c77bc1b04adc8df6219b226c64b80d3a611198`.
- Districts may split tracts; every block remains whole. This result splits
  **60 tracts** across districts.

Population numbers are sums of the published Census counts. Census block
populations are not exact household locations. The solver uses TIGER internal
points, not population-weighted centroids, in a Kansas-centered equirectangular
projection, consistent with the existing tract pipeline. Display coordinates
retain the source NAD83 longitude/latitude; area diagnostics use an approximate
local planar projection.

## Measured runtime and memory

One local run on Windows 10, AMD Ryzen 7 3700X (8 cores, 16 logical processors),
approximately 16 GiB RAM, Python 3.11.3. Package versions: NumPy 2.4.4,
SciPy 1.17.1, pyshp 3.0.3, Shapely 2.1.2. These are observed desktop timings,
not an isolated multi-run performance study or an estimate for other states.

| Phase | Wall time |
|---|---:|
| Validate cached source hash | 0.16 s |
| Extract source archive | 0.21 s |
| Read and validate all block records | 2.57 s |
| Solve four districts | **20.81 s** |
| Validate geometry, dissolve, simplify, shard, and gzip maps | **197.91 s** |
| Timed pipeline, including checkpoint/report preparation | **222.07 s (3 min 42 s)** |

The archive was downloaded before the timed Python pipeline. The download
command took approximately **4.16 s** in this session; network performance is
separate from computation. Python startup and imports precede the pipeline
timer. No algorithm changes were made for this run.

- **Peak Python process working set: 532.92 MiB**, obtained from Windows's
  process high-water counter, including imports and geometry processing.
- Solver phase sampled peak: **169.46 MiB**; phase memory is sampled every
  100 ms and may miss short spikes. The overall OS peak does not use sampling.
- Memory figures exclude the browser and downloader process.

The solver used seed `20200955`, at most 80 outer iterations and 300 inner
iterations, with a center-movement tolerance of 0.0001 m. Centers stabilized
after **22 iterations**. Center convergence alone is not a population or
connectivity acceptance criterion.

## Population balance and connectivity

Ideal population per district: **734,470**.

| Display district | Population | Deviation | Polygon components | Residents outside main polygon |
|---|---:|---:|---:|---:|
| 1 | 734,523 | +53 | 3 | 0 |
| 2 | 734,458 | -12 | 5 | 6 |
| 3 | 734,537 | +67 | 3 | 0 |
| 4 | 734,362 | -108 | 11 | 249 |

- Maximum absolute deviation: **108 people (0.01470%)**.
- Largest-to-smallest population range: **175 people (0.02383% of ideal)**.
- Existing saved Kansas tract result: maximum deviation **1,123 people**.
  The block result reduces that measure by approximately **10.4 times**.
  This compares saved plans, not a fresh controlled timing comparison.
- All source polygons are valid; no geometry repairs were needed. There are
  no multipart source blocks. Dissolved and simplified district coverages are
  valid, with only floating-point-scale overlap/area reconciliation residuals.
- **The result fails shared-edge contiguity.** Four single-polygon blocks
  carrying **255 residents** lie outside their district's largest polygon.
  A follow-up intersection check distinguishes three genuinely detached blocks
  (**249 residents**) from one block (**6 residents**) that touches the main
  polygon at a single point, with no shared boundary segment. The three
  populated detached blocks are approximately 93–257 m from their district's
  main polygon in the local equirectangular plane. Additional detached or
  point-touching blocks have zero population. Each block's internal point is
  inside its assigned complete district geometry. The initial component-count
  diagnostic alone did not distinguish point contacts from actual gaps.

Connectivity requires a block adjacency constraint or explicit repair followed
by rebalancing and revalidation before the demo presents this as a contiguous
plan. No repair was applied during this benchmark, so the measurements describe
the existing solver honestly. Coverage was checked against all source blocks,
not against a separate state-boundary dataset.

## Map payloads

Sizes are actual saved file sizes, compressed with deterministic gzip level 9.
They exclude the application shell and HTTP headers. District outlines are
dissolved from the full block assignments, then simplified with shared-edge
coverage simplification; display simplification never changes populations or
assignments. Full-precision block coordinates remain available in county files.

| Map request | Raw bytes | Gzip bytes | Gzip size |
|---|---:|---:|---:|
| Kansas national overview outlines | 56,444 | 14,725 | **14.4 KiB** |
| State outlines + county detail index | 287,597 | 84,359 | **82.4 KiB** |
| Full unsimplified district outlines | 1,128,983 | 308,811 | 301.6 KiB |
| All 105 county block files | 211,058,624 | 52,714,255 | **50.3 MiB** |
| Largest county file: Johnson | 8,501,622 | 2,106,561 | **2.01 MiB** |
| Sedgwick detail: 12,158 blocks | 8,702,997 | 2,055,190 | **1.96 MiB** |

The median county detail file is 422.4 KiB compressed. A national map can load
only national outlines; clicking Kansas can load state outlines and the small
detail index; block geometry can wait until the visitor zooms into an area.
These are county-shard measurements, not vector-tile performance claims.

The state and national display tolerances are respectively 30 m and 250 m
in the approximate projected plane, using coverage Visvalingam-Whyatt
simplification. These values describe square roots of removed triangle areas,
not strict maximum boundary-displacement bounds. Shared edges remain consistent.

## Browser verification

A separate local viewer successfully rendered the national and state maps and
loaded only Sedgwick's block file on request. A local server served the saved
gzip files with `Content-Encoding: gzip`; browser Resource Timing confirmed the
encoded and decoded sizes.

| Resource | JSON parse | Path generation / Canvas drawing |
|---|---:|---:|
| National outlines | 0.5 ms | 14.6 ms |
| State outlines | 1.2 ms | 15.6 ms |
| Sedgwick blocks | 48.2 ms | 354.6 ms |

These are single local browser observations and exclude browser paint. Local
fetch times do not predict deployed download latency. Browser heap memory was
not measured. The detailed county layer uses Canvas; district outlines use SVG.

## Reproduce and inspect

From the repository root in PowerShell:

```powershell
.\venv\Scripts\python.exe scripts/benchmark_kansas_blocks.py
.\venv\Scripts\python.exe scripts/serve_district_benchmark.py
```

The first command downloads the official archive if absent, reruns the solver,
and generates artifacts under `.cache/kansas-block-benchmark/run-435/`.
The server binds only to `127.0.0.1:8767` and serves compressed artifacts. The
benchmark does not replace application maps. `--solve-only` and
`--resume-export` allow separately labeled solve/export runs.

Saved local artifacts:

- `benchmark.json`: full timing, memory, source hashes, environment, quality,
  and all county payload sizes.
- `solver-result.json`: all 172,529 assignments and numerical solver output.
- `fragmentation.json`: independent population and component check.
- `maps/map-manifest.json`: geometry diagnostics and map-loading scenarios.
- `index.html`: the verified standalone benchmark viewer, generated for this
  experiment. It embeds D3 and needs the local server for its data requests.

Large artifacts and the viewer are ignored cache files. The scripts and this
report are reviewable repository changes; no commit was created.

The follow-up [shared-edge connectivity benchmark](kansas-connectivity-benchmark.md)
repairs this plan and rebalances it, preserving the original measurements here.
This four-district result does not establish runtime or balance at the largest
House-size anchor, where Kansas would receive many more districts.
