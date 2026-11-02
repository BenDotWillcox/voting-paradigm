# Kansas block-resolution House-anchor benchmark — October 22, 2026

**All five anchors completed with every district connected.** The cached graph
loads in 0.94–1.48 seconds. Kansas's 98-district endpoint takes **43.23 minutes**
end to end and finishes within **30.63 people (0.10218%)** of ideal population.
The current numerical solver is the limiting cost at this size, and it reaches
its iteration budgets. The four smaller cases take 3.75–4.80 minutes including
full map export, with at most 1.12 people of final deviation.

The complete measurements and provenance are in
[kansas-anchor-benchmark.json](kansas-anchor-benchmark.json).

## Scope and controls

The five app anchors allocate **4, 5, 6, 9, and 98 districts** to Kansas using
the existing Huntington–Hill apportionment implementation. Apportionment uses
Kansas's 2020 apportionment population, including the overseas allocation;
district balance uses the **2,937,880 residents** in the block source.

Every run includes all **172,529 census blocks**, including **63,380
zero-population blocks** and **3,210 water-only blocks**. Tracts may split;
individual blocks remain whole. The source archive and block order are the
same as the [original block benchmark](kansas-block-benchmark.md) and
[connectivity follow-up](kansas-connectivity-benchmark.md).

Each anchor runs serially in its own fresh Python process. Settings are fixed:
seed `20200955`, 80 outer iterations, 300 inner iterations per solve,
center-movement tolerance `0.0001 m`, and at most 1,000 rebalancing moves.
The numerical solver, repair algorithm, and map exporter are unchanged.
Instrumentation records inner optimizer status without changing its inputs,
outputs, tie rules, or RNG use. Every run exports all map artifacts and
independently validates both graph and polygon connectivity.

These are single desktop observations, not repeated isolated performance
estimates. Hardware/software match the earlier benchmarks: Ryzen 7 3700X,
roughly 16 GiB RAM, Windows 10, Python 3.11.3, NumPy 2.4.4, SciPy 1.17.1,
pyshp 3.0.3, Shapely 2.1.2, and GEOS 3.13.1.

## Reusable shared-edge graph

The **408,475-edge graph** is stored as a **2,673,004-byte (2.55 MiB) compressed
NPZ** containing integer CSR arrays and JSON metadata. Loading disallows
pickle. The cache identity includes the verified source archive SHA-256,
ordered GEOID digest, graph-builder implementation hash, topology rule,
schema version, Shapely version, and GEOS version. Reads validate checksums,
index ranges, sorted unique neighbors, symmetry, and metadata. Invalid entries
are rebuilt and replaced atomically.

The source archive is reverified and extracted before each benchmark. A graph
cache hit avoids rereading geometry for adjacency; it does not bypass source
validation. Shared-edge rules are unchanged: disjoint polygon interiors and a
positive-length shared boundary; corners do not count, water blocks do, and
there is no minimum corridor width.

One-time cache creation took **39.36 s** to build the graph and **1.54 s** to
validate/compress/write it. Including source validation and record reading,
preparation took **43.99 s**, peaking at **392.92 MiB**. This is separate from
the anchor runs. The suite's subsequent preparation check was a cache hit;
each cap also measures its own cache load. Original build timings retained in
cache metadata are provenance, not repeated work.

## Runtime and memory

| House size | KS districts | Graph load | Numerical solve | Repair + rebalance | Full map export | Full pipeline | Peak Python memory |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 435 | 4 | 0.95 s | 19.95 s | 1.71 s | 196.87 s | 225.28 s | 561.71 MiB |
| 574 | 5 | 0.96 s | 73.09 s | 1.68 s | 196.71 s | 278.10 s | 544.62 MiB |
| 692 | 6 | 0.94 s | 83.54 s | 1.90 s | 196.10 s | 288.07 s | 534.61 MiB |
| 1,000 | 9 | 1.04 s | 47.87 s | 1.74 s | 195.47 s | 251.90 s | 507.27 MiB |
| 11,037 | 98 | 1.48 s | 2,297.05 s | 67.37 s | 221.18 s | 2,593.58 s | 677.29 MiB |

Full pipeline time also includes source verification/extraction, input reads,
checkpoints, and independent graph audits. Python startup/imports precede its
timer; suite wall time includes process startup. Overall memory is the Windows
process working-set high-water mark; phase peaks are sampled every 100 ms.
Browser, server, and parent orchestration memory are excluded.

The cached four-district control exactly reproduces both the original initial
assignments and the earlier corrected assignments, with matching source hashes.
Its graph-load phase is 0.95 s versus the earlier 45.81 s rebuild. Total time
also varies with solver/export timing and instrumentation; the entire observed
pipeline difference must not be attributed to caching.

At 98 districts, the solve accounts for **88.6%** of the pipeline. Its sampled
memory peak rises to **672.30 MiB**, compared with 176.92–204.86 MiB at the
smaller anchors. Export dominates overall peak memory in the smaller cases;
their declining whole-process peaks do not mean solver memory declines with
district count. The five fresh-process runs and warm cache preparation take
**60.78 minutes** in total, excluding the separately measured cold preparation.

## Connectivity and population balance

Deviation is measured against the common fractional ideal `2,937,880 / K`,
using exact integer numerators internally. It is not rounded down to an
integer target. The integer-person lower bound assumes people can be allocated
individually; whole-block and connectivity constraints may prevent reaching it.

| House size | Initial max deviation (people) | After repair (people) | After rebalance (people) | Final deviation % | All districts connected? |
|---:|---:|---:|---:|---:|---|
| 435 | 108 | 351 | 0 | 0% | Yes, graph and polygons |
| 574 | 301 | 338 | 0 | 0% | Yes, graph and polygons |
| 692 | 499.666667 | 1,002.666667 | 0.666667 | 0.00013615% | Yes, graph and polygons |
| 1,000 | 202.888889 | 290.888889 | 1.111111 | 0.00034038% | Yes, graph and polygons |
| 11,037 | 657.632653 | 657.632653 | 30.632653 | 0.10218253% | Yes, graph and polygons |

- Four districts each contain **734,470** people; five each contain **587,576**.
- Six districts attain the integer-person optimum: two contain **489,646**
  and four contain **489,647**. Their two-thirds-person worst deviation is the
  mathematical lower bound, not a population estimation error.
- Nine districts contain **326,430–326,432** people. The local search stops
  at a worst deviation of `10/9` people, versus the integer-person lower bound
  `8/9`. This does not prove no better whole-block plan exists.
- The 98 districts contain **29,966–30,009** people, against an ideal of
  **29,978.367347**. Their 43-person total range is **0.14344%** of ideal.
  Repair makes 69 component transfers; rebalancing makes 333 single-block
  moves. Overall, 431 blocks containing 9,232 people change districts.
  The arithmetic lower bound is `31/49` people; its feasibility with whole
  blocks and shared-edge connectivity remains unknown.

Each completed case has one graph component and one dissolved polygon per
district, all blocks assigned once, and matching source/assignment/map
population totals. Coverage is valid; tiny nonzero summed-area residuals
reflect floating-point geometry measurements. Exact adjacency is evaluated
on original coordinates, with no snapping or buffering.

## Solver and search limits

| House size | Outer iterations | Centers settled? | Inner passes hitting limit | Rebalance moves | Search stop |
|---:|---:|---|---:|---:|---|
| 435 | 22 | Yes | 0 | 9 | Local optimum |
| 574 | 80 | No | 0 | 11 | Local optimum |
| 692 | 80 | No | 0 | 19 | Local optimum |
| 1,000 | 42 | Yes | 0 | 14 | Local optimum |
| 11,037 | 80 | No | 72 of 81 | 333 | Local optimum |

All inner solves succeed at the four smaller anchors, although the five- and
six-district center loops hit their 80-iteration cap. At 98 districts, the
center loop also hits that cap and **72 of 81 inner solves exhaust their
300-iteration budget**. The remaining nine report success by relative
objective reduction. The final result is an iteration-limited initial plan
followed by connectivity repair and local rebalancing, not a converged optimum.
No anchor hits the 1,000-move rebalancing cap. Raising that cap alone would not
change a local-optimum stop.

Center convergence, optimizer status, connectivity, and population balance are
distinct checks. Repaired plans are no longer exact power diagrams. The local
search considers improving single populated-block transfers, not simultaneous
swaps or neutral moves; compactness is not an acceptance constraint.

## Saved map payloads

These are gzip body bytes, excluding the viewer and HTTP headers. The national
view needs only simplified district outlines; state entry adds more detailed
outlines and the county index. Full block coordinates remain lazy county files.

| House size | National outlines | State outlines + county index |
|---:|---:|---:|
| 435 | 13,706 B | 81,219 B |
| 574 | 16,541 B | 92,693 B |
| 692 | 15,886 B | 98,453 B |
| 1,000 | 22,023 B | 131,250 B |
| 11,037 | 104,554 B | 457,627 B |

At 98 districts, that is **102.10 KiB** for Kansas's national outlines and
**446.90 KiB** for state entry. Exact district outlines are **1.57 MiB**.
The county index lets the client request only the desired block detail:

| House size | All county detail, gzip | Largest lazy county shard, gzip |
|---:|---:|---:|
| 435 | 52,714,254 B | 2,106,559 B |
| 574 | 52,714,788 B | 2,107,567 B |
| 692 | 52,719,603 B | 2,108,210 B |
| 1,000 | 52,721,957 B | 2,109,253 B |
| 11,037 | 52,786,152 B | 2,117,785 B |

Across anchors, all block detail is **50.27–50.34 MiB** compressed; the largest
county shard is **2.01–2.02 MiB**. More districts substantially increase outline
complexity. Block coordinates remain unchanged; assignment labels slightly
change detail payload size. These are
saved payload sizes, not browser memory or network-latency benchmarks.

## Implication for precomputation

The graph can be shared across all Kansas seat counts and seeds. Even the
endpoint fits comfortably within this machine's memory and produces connected
saved maps, supporting the proposed offline computation and lazy-detail
delivery. This run does not establish the cost or feasibility for all states
or every seat count. The endpoint's 38.3-minute solve and iteration-limit
flags make numerical performance and stopping behavior the next issues to
investigate before scaling the full precompute range.

Code inspection suggests repeated allocation and scans of the dense
block-by-district score matrix as one optimization target. That is an
unprofiled hypothesis; no solver optimization or speedup is claimed here.

## Reproduce and inspect

```powershell
.\venv\Scripts\python.exe scripts/run_kansas_anchor_suite.py --output .cache/kansas-block-benchmark/anchor-suite-repeat
```

Use a fresh output directory. The suite prepares the shared graph cache in a
separate process, then runs every anchor serially. For one anchor, invoke
`scripts/benchmark_kansas_anchors.py --house-size 11037 --output <new-directory>`.
The default graph cache is `.cache/kansas-block-benchmark/graph-cache/`.

Every cap saves an initial checkpoint, repaired assignments, final assignments,
move audit, source/code/settings hashes, solver telemetry, complete report,
and map manifest. The suite retains each process log and aggregates completed
reports in `suite.json`. Large source and map artifacts remain ignored cache
files. The app's tract maps are unchanged.

The local inspection viewer is available at
[Kansas, House size 11,037](http://127.0.0.1:8769/house-11037/), with links to
every other anchor. It loads saved national outlines first, state outlines
and the county index on demand, then only the selected county's blocks. To
restart the local server while the cached viewer files are present:

```powershell
.\venv\Scripts\python.exe scripts/serve_district_benchmark.py --directory .cache/kansas-block-benchmark/anchor-suite --port 8769
```

The focused districting/script suite has **138 passing tests**, including
cache corruption/invalidation, fractional population metrics, observer
invariance, connectivity, and deterministic moves. All five recorded code
hash sets match the sources after the run; compilation checks and
`git diff --check` pass. Browser verification covered the 98-district national
and state views, a selected district's population, lazy loading of Sedgwick's
12,158 blocks, and clearing that detail. No commit was created.
