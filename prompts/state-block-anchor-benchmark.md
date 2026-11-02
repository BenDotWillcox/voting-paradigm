# Remaining-state census-block anchor benchmark — October 23, 2026

**Later correction:** Maryland K19 and Virginia K26 now have separately versioned, validated replacements, bringing available valid plans to **154**. See the [part-connectivity correction report](maryland-virginia-part-connectivity-fix.md). The measurements and counts below preserve the original batch snapshot, including its two failed attempts.

**The batch is finished: 152 validated plans, 23 topology exceptions, and two polygon-validation failures.** All benchmark/recovery processes have exited and the queue plus all 49 state locks are free. Forty states have valid plans at all four requested anchors; Maryland and Virginia have valid plans below House size 1,000. No synthetic connections were added.

[Full measurements, per-plan results, provenance, and verification](state-block-anchor-benchmark.json) accompany this report. [Local results and maps](http://127.0.0.1:8770/) remain available while the viewer server is running. The app continues to serve its existing tract plans; this offline block benchmark does not replace them.

## Scope and measurement

The scope is the 49 states excluding Kansas, at House sizes **435 / 574 / 692 / 1,000**, omitting 11,037. Equal state seat counts reuse one plan, giving 177 distinct state/count jobs. Census blocks remain whole, including zero-population and water blocks; tracts may split. Shared-edge adjacency requires disjoint interiors and positive-length shared boundaries on source coordinates. Corner contacts do not count; no snapping, buffering, or artificial water bridges is used.

Apportionment uses the existing 2020 apportionment totals. District balance uses verified **resident population / district count**, retaining the fractional ideal. Settings remain seed 20200955, 80 outer iterations, 300 inner iterations, center tolerance 0.0001 m, and at most 1,000 rebalancing moves. The 13 recorded numerical/source implementation hashes were unchanged through recovery.

All aggregate performance/balance statistics below use the **152 complete plans only**, excluding rejected source topologies and the two failed exports. Overall statistics count each unique state/count once; an anchor table may reuse the same plan. These are selected completed outputs, not evidence that every state topology is supported. “Complete” certifies saved output and connectivity, not a specified population-tolerance target or global optimality.

## Runtime and memory

The original two-worker batch ran for **10 h 44 min 11.83 s** (October 22, 5:16:59 p.m. to October 23, 4:01:10 a.m. CT). Separate serial recovery ran for **6 h 8 min 39.86 s** (October 23, 4:35:27–10:44:06 a.m. CT). Original batch start, finish, elapsed time, terminal manifest, and failed-attempt history are preserved. Recovery timings are additional and are not folded into the original batch timing.

Median complete-plan pipeline time is **6.50 minutes**; the 90th percentile is **17.65 minutes**. Median per-process peak working set is **634.59 MiB**, with a maximum of **2.23 GiB** in Texas K88. Pipeline time includes source preparation, solve, correction, validation, and export; Python startup is excluded. Browser/server/parent memory and other simultaneous workers are excluded from per-process memory. Concurrent original timings and serial recovery timings are not isolated head-to-head comparisons.

| House size | Complete states | Median pipeline (min) | 90th percentile (min) | Slowest (min) | Worst final deviation |
|---:|---:|---:|---:|---:|---:|
| 435 | 42 | 5.84 | 11.93 | 69.54 | 0.001300% |
| 574 | 42 | 6.06 | 14.81 | 84.31 | 2.253590% |
| 692 | 42 | 5.81 | 15.70 | 108.13 | 0.003580% |
| 1000 | 40 | 7.16 | 23.35 | 156.19 | 0.006093% |

Texas is the runtime outlier; outside Texas the slowest complete plan is Pennsylvania K39 at 34.47 minutes.

| House size | Texas districts | Pipeline (min) | Peak memory (MiB) | Max deviation (people) | Max deviation (%) |
|---:|---:|---:|---:|---:|---:|
| 435 | 38 | 69.54 | 1759.55 | 9.974 | 0.001300% |
| 574 | 51 | 84.31 | 1720.02 | 8.490 | 0.001486% |
| 692 | 61 | 108.13 | 1731.04 | 11.836 | 0.002477% |
| 1000 | 88 | 156.19 | 2281.79 | 15.080 | 0.004553% |

Texas K88 spent **137.17 minutes solving**, **2.37 minutes repairing/rebalancing**, and **16.12 minutes validating/exporting maps**. It reached the outer iteration limit; its final balance and connectivity were measured independently. Across the complete set, 90 solves reached the outer limit. A solver iteration limit does not itself imply invalid output, nor does valid output establish numerical convergence.

Graph preparation among complete plans had a cold median of **47.54 s** (42 first plans) and a warm median of **0.93 s** (110 hits). These are different samples, not a controlled speedup ratio. Texas provides a direct state example: 197.96 s cold versus 4.13–4.28 s cached. Source identity checks still run on cache hits.

## Population balance and connectivity

**151 of 152 complete plans have maximum district deviation below 25 people and below 0.01%.** In 139 plans it is at most 10 people. The median plan's maximum deviation is 2.817 people; the 90th percentile is 9.415 people. These measures describe the worst district within each plan, not average district error.

**West Virginia K3 (House 574) is the exception:** initial disconnected assignments were within 5.33 people of ideal. Component repair established connectivity but raised maximum deviation to 53,875.33 people (9.01068%). After 1,000 rebalancing moves, it remained at **13,474.33 people (2.25359%)**, with district populations 597,919 / 584,431 / 611,366. The search stopped at its move budget, not a demonstrated optimum. This plan is connected but requires further balancing work. The other 151 complete plans stopped at a local optimum under the implemented moves; that is not a global-optimality certificate.

All **1,879 district instances** across the 152 plans pass shared-edge graph connectivity and independent **unsimplified single-component polygon** validation. Every source block is assigned once, source population reconciles, and saved geometry/coverage audits pass. Of these plans, **146 initially had disconnected assignments**; correction made **6,582 component-repair moves** and **7,633 subsequent rebalancing moves**. The corrected result is not an exact power diagram; convex continuous power cells alone do not certify whole-block connectivity.

## Exceptions and failures

| State | Distinct jobs flagged | Reason |
|---|---:|---|
| Alaska | 2 | Antimeridian-spanning source geometry needs normalization before current topology/export adapters can certify it. |
| Rhode Island | 2 | Source graph has 2 components. |
| Hawaii | 3 | Source graph has 17 components. |
| Kentucky | 4 | Source graph has 2 components. |
| New York | 4 | Source graph has 3 components. |
| Florida | 4 | Source graph has 2 components. |
| California | 4 | Source graph has 7 components. |

These **23 source-topology exceptions** were rejected before solving under the strict policy. Source-graph rejection is a workflow limitation, not generally proof that no connected partition exists. A state/count may reuse its state's preflight exception rather than rerunning it.

Two separate **geometry failures** remain failed, with artifacts preserved and no unchanged retry:

- **Maryland K19 / House 1,000:** block graph audit passed, but display District 17 (index 16) has three unsimplified polygon components.
- **Virginia K26 / House 1,000:** block graph audit passed, but display District 19 (index 18) has two unsimplified polygon components.

Representing multipart source blocks as single graph nodes is a plausible explanation for graph/polygon disagreement; the exact source pieces causing these failures were not established. The independent polygon validation correctly prevents treating these outputs as complete.

## Compressed map payloads

| Saved gzip payload | Median | Range |
|---|---:|---:|
| National district outlines for one state/plan | 40.9 KiB | 1.18–308.6 KiB |
| State entry: district outlines + county index | 204.2 KiB | 4.45 KiB–1.35 MiB |
| One county of full block detail | 0.831 MiB | 20.7 KiB–13.79 MiB |
| All county details for one state/plan | 68.11 MiB | 6.96–243.05 MiB |

Outline/state distributions cover 152 plans; county statistics cover 10,090 shards, including the same counties under different plans. Summing national outlines for the available complete states at each anchor gives:

| House size | Included states | Combined gzip outlines |
|---:|---:|---:|
| 435 | 42 | 1.44 MiB |
| 574 | 42 | 1.69 MiB |
| 692 | 42 | 1.85 MiB |
| 1000 | 40 | 2.14 MiB |

These totals **exclude Kansas and every missing/failed state at that anchor**. They are artifact-size estimates, not measured initial browser downloads; manifests, reports, HTML/JS/CSS, basemaps, headers, and other overhead are excluded.

For Texas K88, national outlines are 315,964 bytes; state entry is 1,413,364 bytes (1.35 MiB). Full detail across all 254 counties is 254,855,962 bytes (243.05 MiB), so it stays behind county-level lazy loading. Harris County alone is 8.93 MiB. The largest county shard overall is **Maricopa, Arizona K22: 13.79 MiB compressed, 57.59 MiB raw, 61,427 blocks**. Large counties remain the main frontend payload concern. Display simplification changes outlines, not assignments or population.

## Operational recovery and verification

Windows progress-file replacement failures interrupted orchestration for Utah, New Jersey, and Texas. Recovery used unchanged numerical code/settings, direct child log files, bounded metadata-write retries, and the original queue/state locks. It ran each of these seven entries once:

| State | Districts | Recovery action | Child wall time (s) |
|---|---:|---|---:|
| Utah | 10 | One retry | 243.74 |
| New Jersey | 16 | Validate/reuse | 2.63 |
| New Jersey | 19 | Deferred first attempt | 327.70 |
| New Jersey | 28 | Deferred first attempt | 611.80 |
| Texas | 51 | One retry | 5060.01 |
| Texas | 61 | Deferred first attempt | 6493.04 |
| Texas | 88 | Deferred first attempt | 9379.52 |

All seven exited with code 0. **NJ16's 2.63-second recovery action only validated/reused its original 365.24-second benchmark**, whose report bytes are unchanged. NJ19/NJ28 and TX61/TX88 were unstarted work, not failed solvers retried. Utah10 and TX51 preserve their prior failed reports; the original national terminal manifest is retained with its SHA-256. Maryland and Virginia geometry failures were never retried.

The final review independently recomputed population deviations from saved district populations and checked all terminal counts/audits, 608 checkpoint/move-audit hashes, 10,698 compressed map file sizes, all 13 frozen code hashes, recovery report hashes, and preserved original timing. Eight representative gzip files passed decompression/CRC and JSON checks; seven GeoJSON files also matched saved raw hashes (the index has no saved raw hash). This was an audit of saved evidence, not a rerun of every graph/geometric calculation or decompression of every county file. No discrepancies were found.
