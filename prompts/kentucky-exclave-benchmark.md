# Kentucky recorded-exclave benchmark

4 accepted plans; 0 failed attempts. All 132,662 source blocks and 4,505,836 residents were retained in every accepted plan.

[Open comparison and maps](http://127.0.0.1:8770/policies/kentucky-exclave-v1/)

| House size | Districts | Max deviation (people) | Max deviation (%) | Pipeline (s) | Solve (s) | Peak MiB | Policy-connected |
|---|---:|---:|---:|---:|---:|---:|---:|
| 435 | 6 | 1.667 | 0.000222% | 573.22 | 22.991 | 1,075.3 | 6/6 |
| 574 | 8 | 3.500 | 0.000621% | 507.30 | 34.544 | 1,069.1 | 8/8 |
| 692 | 9 | 1.556 | 0.000311% | 491.81 | 24.152 | 1,075.6 | 9/9 |
| 1000 | 14 | 3.571 | 0.001110% | 577.63 | 87.469 | 1,075.4 | 14/14 |

**Outer convergence caveat:** 14-district run: The outer loop reached the 80-iteration limit without center convergence. Successful inner optimizer passes do not establish outer convergence. Final population balance and connectivity are assessed separately after repair/rebalancing.

## Connectivity and the geographic exception

The same recorded Kentucky Bend connection spans 5.145 km: 1.805 km of 2020 mapped river water and 3.340 km of Missouri land. It is explicitly an exclave graph connection, not a water-only route or a change to district territory. Missouri coverage appears only as context. Physical and policy polygon counts below remain distinct.

### 6 districts

[Map](http://127.0.0.1:8770/policies/kentucky-exclave-v1/states/21/districts-6/) · [Saved benchmark](C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/policies/kentucky-exclave-v1/states/21/districts-6/benchmark.json)

Populations: 750,974 / 750,973 / 750,971 / 750,972 / 750,973 / 750,973.

Physical polygon components by district: [1, 1, 2, 1, 1, 1]. Components after the recorded connection: [1, 1, 1, 1, 1, 1]. The one link is used by District 3; both endpoint GEOIDs independently match that district in final assignments.

All 43 inner optimizer passes succeeded. The outer loop met its center-convergence tolerance after 42 iterations. Successful inner optimizer passes do not establish outer convergence. Final population balance and connectivity are assessed separately after repair/rebalancing.

Postprocessing stopped at `local_optimum`. Repair / part-repair / rebalance moves: 15 / 0 / 14.

Compressed district outlines: national: 34.7 KiB / state: 201.9 KiB / full: 893.1 KiB. Connection: 1,483 bytes.

### 8 districts

[Map](http://127.0.0.1:8770/policies/kentucky-exclave-v1/states/21/districts-8/) · [Saved benchmark](C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/policies/kentucky-exclave-v1/states/21/districts-8/benchmark.json)

Populations: 563,230 / 563,231 / 563,226 / 563,229 / 563,231 / 563,231 / 563,229 / 563,229.

Physical polygon components by district: [1, 1, 2, 1, 1, 1, 1, 1]. Components after the recorded connection: [1, 1, 1, 1, 1, 1, 1, 1]. The one link is used by District 3; both endpoint GEOIDs independently match that district in final assignments.

All 67 inner optimizer passes succeeded. The outer loop met its center-convergence tolerance after 66 iterations. Successful inner optimizer passes do not establish outer convergence. Final population balance and connectivity are assessed separately after repair/rebalancing.

Postprocessing stopped at `local_optimum`. Repair / part-repair / rebalance moves: 24 / 0 / 38.

Compressed district outlines: national: 44.8 KiB / state: 251.2 KiB / full: 1134.5 KiB. Connection: 1,483 bytes.

### 9 districts

[Map](http://127.0.0.1:8770/policies/kentucky-exclave-v1/states/21/districts-9/) · [Saved benchmark](C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/policies/kentucky-exclave-v1/states/21/districts-9/benchmark.json)

Populations: 500,648 / 500,650 / 500,647 / 500,647 / 500,650 / 500,649 / 500,649 / 500,649 / 500,647.

Physical polygon components by district: [1, 1, 2, 1, 1, 1, 1, 1, 1]. Components after the recorded connection: [1, 1, 1, 1, 1, 1, 1, 1, 1]. The one link is used by District 3; both endpoint GEOIDs independently match that district in final assignments.

All 42 inner optimizer passes succeeded. The outer loop met its center-convergence tolerance after 41 iterations. Successful inner optimizer passes do not establish outer convergence. Final population balance and connectivity are assessed separately after repair/rebalancing.

Postprocessing stopped at `local_optimum`. Repair / part-repair / rebalance moves: 36 / 0 / 23.

Compressed district outlines: national: 47.3 KiB / state: 246.5 KiB / full: 1075.3 KiB. Connection: 1,483 bytes.

### 14 districts

[Map](http://127.0.0.1:8770/policies/kentucky-exclave-v1/states/21/districts-14/) · [Saved benchmark](C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/policies/kentucky-exclave-v1/states/21/districts-14/benchmark.json)

Populations: 321,845 / 321,849 / 321,843 / 321,843 / 321,846 / 321,847 / 321,846 / 321,844 / 321,843 / 321,846 / 321,847 / 321,844 / 321,845 / 321,848.

Physical polygon components by district: [1, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]. Components after the recorded connection: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]. The one link is used by District 3; both endpoint GEOIDs independently match that district in final assignments.

All 81 inner optimizer passes succeeded. The outer loop reached the 80-iteration limit without center convergence. Successful inner optimizer passes do not establish outer convergence. Final population balance and connectivity are assessed separately after repair/rebalancing.

Postprocessing stopped at `local_optimum`. Repair / part-repair / rebalance moves: 44 / 0 / 56.

Compressed district outlines: national: 62.3 KiB / state: 339.1 KiB / full: 1513.5 KiB. Connection: 1,483 bytes.

## Strict baseline and interpretation

The preserved strict K6 attempt stopped at source-topology preflight after 66.1568065 seconds. K8/K9/K14 reused that exception. There are no prior strict solved populations or solver runtimes to compare; no speedup over a strict solver is claimed.

## Validation and timing limits

Independently read the original source DBF, verified unique GEOIDs and official totals, and recomputed final district totals from saved assignments. Checked compressed-map sizes and decompressed hashes, declared policy validation, same-district endpoints, identical source connection records across K, and 275 preserved historical file hashes.

415 districting and benchmark regression tests plus 14 independent comparison-verifier tests passed. Browser checks verified all four plan displays, connection overlays and ownership, the connection toggle, and K6 exact outlines with lazy county-block loading.

- New plans run serially in fresh processes with cached source and part graphs; shared-desktop timings are observations, not isolated hardware comparisons.
- Full pipeline includes source preparation, link preparation, solve, repair/rebalance, independent polygon validation, map export, viewer generation and preservation checks.
- Process imports, initial preservation inventory and final report flush are outside the pipeline timer.
- Strict topology rejection happened before solving; it is not a before/after solver-performance baseline.
- Physical shared-edge connectivity and policy connectivity are separate. The recorded exclave connection crosses Missouri land and water; no Missouri area or population is assigned.
- Population deviations are independently recomputed from source DBF and final assignments. Local whole-block balancing does not establish global optimality.
- Successful inner optimizer passes, outer center convergence, final postprocessed population balance and policy connectivity are independent outcomes. Outer iteration-limit cases are disclosed explicitly.
- Compressed payloads measure saved map bytes, not browser memory or latency. Missouri diagnostic context loads only on connection/Bend inspection and is separate from the map export sizes.

[Water/land crossing audit](C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/diagnostics/kentucky/area-water-audit.json) · [Original diagnosis](http://127.0.0.1:8770/diagnostics/kentucky/) · [Machine-readable comparison](C:/Users/benja/projects/voting_paradigm/prompts/kentucky-exclave-benchmark.json)
