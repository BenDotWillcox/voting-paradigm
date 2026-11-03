# Rhode Island: recorded island-water connections

Both requested plans now pass polygon-part and independent polygon connectivity **under the recorded water-link policy**. All 25,649 blocks and 1,097,379 residents remain covered exactly. The original strict exception, diagnostic witness, source archive and national suite are byte-identical.

[Comparison](http://127.0.0.1:8770/policies/island-water-v1/) · [2-district map](http://127.0.0.1:8770/policies/island-water-v1/states/44/districts-2/) · [3-district map](http://127.0.0.1:8770/policies/island-water-v1/states/44/districts-3/) · [Original strict diagnosis](http://127.0.0.1:8770/diagnostics/rhode-island/) · [Strict connectivity-only example](http://127.0.0.1:8770/diagnostics/rhode-island/connectivity-only-k2/). Use **Inspect connection** on either new map; the magenta dashed line is enabled by default and is not land.

| Districts | House sizes | New populations | Strict maximum deviation | New maximum deviation |
|---|---|---|---|---|
| 2 | 435, 574, 692 | 548,690, 548,689 | 99.743024% | 0.000091126% (0.5 person) |
| 3 | 1000 | 365,792, 365,794, 365,793 | ≥ 99.614536% | 0.000273379% (1 person) |

The strict K2 figure is attained by assigning one district to each source component. Strict K3 is a necessary lower bound, not a constructed plan. New population balance is measured independently of connectivity.

| Districts | Full pipeline | Link preparation | Solve | Repair/balance | Polygon audit/export | Peak working set |
|---|---:|---:|---:|---:|---:|---:|
| 2 | 70.50 s | 16.47 s | 0.286 s | 0.374 s | 51.06 s | 218.4 MiB |
| 3 | 71.68 s | 16.76 s | 1.245 s | 0.389 s | 51.17 s | 217.9 MiB |

Runs used fresh processes serially, with cached source and physical graphs. Full pipeline includes preparation, audits, export and report work; remaining phase timings are in the JSON. These are shared-desktop observations. The original strict run took **8.4581 seconds to reject source topology before solving**. K3 reused that exception without its own run. There is no strict-solver timing baseline or speedup claim.

| Districts | Outer iterations / centers converged | Repair / balance moves | Stop reason | Physical → policy polygon components | Link used by district |
|---|---|---|---|---|---|
| 2 | 6 / yes | 0 / 0 | local_optimum | [1, 2] → [1, 1] | 2 |
| 3 | 13 / yes | 2 / 4 | local_optimum | [1, 1, 2] → [1, 1, 1] | 3 |

One shortest-boundary connection links blocks **440099901000017** and **440099902000001** across **2,334.777 m of census-coverage gap**. Both endpoints belong to the indicated district. Source geometry is unchanged: a district using the link still has two physical polygons, so pure shared-edge polygon validation remains false, while the declared policy passes. The rooted forest rule permits small-island chains without cycles or links between two sufficiently populated roots.

The **1% band only classifies undersized components** (below 99% of ideal); it is not final-plan acceptance or solver tolerance. The local bbox-centered distance differs slightly from the earlier 2,333.895 m population-centered diagnostic. Neither measures shore-to-shore distance or a ferry route.

Numerical settings remain seed **20200955**, outer limit **80**, inner limit **300**, center tolerance **0.0001 m**, and **1,000** maximum balancing moves. No numerical solver was modified. Whole-block local optimization does not generally guarantee these population results elsewhere.

Validation: **308 regression tests passed**. Both maps were checked in-browser with exact outlines, connection toggles and focus; county 009 loaded its 4,341 blocks on demand.

Evidence: [K2 report](/C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/policies/island-water-v1/states/44/districts-2/benchmark.json) · [K3 report](/C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/policies/island-water-v1/states/44/districts-3/benchmark.json) · [Compact comparison JSON](/C:/Users/benja/projects/voting_paradigm/prompts/rhode-island-water-benchmark.json) · [Runner](/C:/Users/benja/projects/voting_paradigm/scripts/benchmark_rhode_island_water.py) · [Link builder](/C:/Users/benja/projects/voting_paradigm/scripts/district_block_island_links.py). Each run records source/code hashes, assignments, moves, connection endpoints, validation and artifact checksums. The source archive SHA-256 is `79d10c9dfec1e3e0962e13d6295b53856db286a156d9937d3737adb0c542f35b`.
