# Florida water-policy benchmark

Florida K28/K37/K45/K65 for House 435/574/692/1000: first census-block solves with the population-aware recorded water policy and 1,000 inner iterations.

Outcome: **complete**. 22 historical files independently rehashed and unchanged.


| Districts | Final maximum deviation | Population range | Policy connected | Physically connected | Largest inner pass |
|---|---:|---:|---:|---:|---:|
| 28 | 41.036 people / 0.005335% | 769,203–769,262 | 28/28 | 27/28 | 237 |
| 37 | 16.162 people / 0.002776% | 582,097–582,125 | 37/37 | 36/37 | 220 |
| 45 | 44.622 people / 0.009323% | 478,598–478,671 | 45/45 | 44/45 | 319 |
| 65 | 40.277 people / 0.012155% | 331,338–331,397 | 65/65 | 64/65 | 442 |

| Districts | Pipeline min | Solver min | Export/validation min | Peak GiB |
|---|---:|---:|---:|---:|
| 28 | 19.76 | 6.49 | 10.76 | 1.576 |
| 37 | 21.66 | 8.46 | 10.50 | 1.571 |
| 45 | 26.52 | 13.27 | 10.40 | 1.564 |
| 65 | 38.82 | 24.88 | 10.43 | 1.513 |

Preparation: 0.412 s. Serial child processes: 106.88 min. Overall launcher elapsed time, including between-run validation: 106.96 min. [Execution record](http://127.0.0.1:8770/policies/florida-water-v1/run.json). All four plans are first water-policy attempts; the strict preflight did not solve a plan.

## House 435: 28 districts

[Validated map](http://127.0.0.1:8770/policies/florida-water-v1/states/12/districts-28/). District 13: 2 physical pieces.
The outer loop reached the 80-iteration limit without center convergence. Successful inner optimizer passes do not establish outer convergence. Final population balance and connectivity are assessed separately after repair/rebalancing.

Connectivity postprocessing: 238 component-repair moves, 0 part-repair moves, and 236/1000 rebalance moves. Rebalancing stopped with **local_optimum**.

| Stage | Maximum deviation people | Maximum deviation % |
|---|---:|---:|
| initial | 1083.964286 | 0.140917153 |
| after repair | 2875.035714 | 0.373759407 |
| final | 41.035714 | 0.005334711 |

All 390,066 blocks and 21,538,187 residents are assigned once. 71 compressed map artifacts verified. Gzip bytes: national 89,726; state entry 419,079; connections 444; all county shards 111,405,636.

| Link | Endpoint districts | Used within district |
|---|---|---|
| fl-water-001 | 13 / 13 | 13 |

81 inner passes; 3,851 accepted iterations; all inner passes succeeded: True.

## House 574: 37 districts

[Validated map](http://127.0.0.1:8770/policies/florida-water-v1/states/12/districts-37/). District 13: 2 physical pieces.
The outer loop reached the 80-iteration limit without center convergence. Successful inner optimizer passes do not establish outer convergence. Final population balance and connectivity are assessed separately after repair/rebalancing.

Connectivity postprocessing: 307 component-repair moves, 0 part-repair moves, and 321/1000 rebalance moves. Rebalancing stopped with **local_optimum**.

| Stage | Maximum deviation people | Maximum deviation % |
|---|---:|---:|
| initial | 1017.162162 | 0.174736156 |
| after repair | 2902.837838 | 0.498672428 |
| final | 16.162162 | 0.002776464 |

All 390,066 blocks and 21,538,187 residents are assigned once. 71 compressed map artifacts verified. Gzip bytes: national 101,826; state entry 465,274; connections 444; all county shards 111,438,470.

| Link | Endpoint districts | Used within district |
|---|---|---|
| fl-water-001 | 13 / 13 | 13 |

81 inner passes; 4,379 accepted iterations; all inner passes succeeded: True.

## House 692: 45 districts

[Validated map](http://127.0.0.1:8770/policies/florida-water-v1/states/12/districts-45/). District 13: 2 physical pieces.
The outer loop reached the 80-iteration limit without center convergence. Successful inner optimizer passes do not establish outer convergence. Final population balance and connectivity are assessed separately after repair/rebalancing.

Connectivity postprocessing: 328 component-repair moves, 0 part-repair moves, and 357/1000 rebalance moves. Rebalancing stopped with **local_optimum**.

| Stage | Maximum deviation people | Maximum deviation % |
|---|---:|---:|
| initial | 487.377778 | 0.101828441 |
| after repair | 3916.622222 | 0.818304716 |
| final | 44.622222 | 0.009322976 |

All 390,066 blocks and 21,538,187 residents are assigned once. 71 compressed map artifacts verified. Gzip bytes: national 124,357; state entry 605,669; connections 444; all county shards 111,451,025.

| Link | Endpoint districts | Used within district |
|---|---|---|
| fl-water-001 | 13 / 13 | 13 |

81 inner passes; 6,896 accepted iterations; all inner passes succeeded: True.

## House 1000: 65 districts

[Validated map](http://127.0.0.1:8770/policies/florida-water-v1/states/12/districts-65/). District 13: 2 physical pieces.
The outer loop reached the 80-iteration limit without center convergence. Successful inner optimizer passes do not establish outer convergence. Final population balance and connectivity are assessed separately after repair/rebalancing.

Connectivity postprocessing: 443 component-repair moves, 0 part-repair moves, and 432/1000 rebalance moves. Rebalancing stopped with **local_optimum**.

| Stage | Maximum deviation people | Maximum deviation % |
|---|---:|---:|
| initial | 921.276923 | 0.278031758 |
| after repair | 1918.276923 | 0.578915951 |
| final | 40.276923 | 0.012155155 |

All 390,066 blocks and 21,538,187 residents are assigned once. 71 compressed map artifacts verified. Gzip bytes: national 144,800; state entry 679,041; connections 444; all county shards 111,494,993.

| Link | Endpoint districts | Used within district |
|---|---|---|
| fl-water-001 | 13 / 13 | 13 |

81 inner passes; 10,165 accepted iterations; all inner passes succeeded: True.

Validation: All four serial children exited with code 0. The process gate verifies original benchmark processes have exited and the state12 lock is free; it records Windows PID reuse using live executable identity and creation time rather than claiming every numerical PID is absent. Prelaunch suite: 999 passed in 33.13s. Original 115-test summary evidence is preserved; updated summary-only PID-reuse checks: 142 passed in 1.03s, independently reviewed. No numerical code or benchmark run changed. This report independently verifies saved source populations, graph and polygon/link connectivity, artifact hashes, compressed maps and historical evidence. Final browser QA is recorded separately after report generation.

[Saved prelaunch test evidence](http://127.0.0.1:8770/policies/florida-water-v1/validation-tests.json): 999 tests passed; the checksum is retained in the comparison JSON.

[Summary validation evidence](http://127.0.0.1:8770/policies/florida-water-v1/summary-validation-tests.json): 142 focused checks passed; the tested summary and test-source hashes are recorded.

- All four targets are first water-policy attempts, run serially; the preserved strict source-topology exception did not solve a plan. This is not a controlled 300-versus-1000 iteration experiment.
- Successful inner solves, outer center convergence, final population balance and connectivity under recorded water links are separate outcomes.
- Physical polygons remain unchanged. The water connection counts only when both endpoint blocks belong to the same district; multipart ownership never creates a geometric edge.
- The single connection joins water-inclusive census coverage in the Dry Tortugas region to main Florida coverage. Its endpoints are not shorelines, a bridge, or a ferry route; official regional attribution is not a global high-resolution shoreline certificate.
- The 1% group/root preflight guides link selection; it is not a final population-balance acceptance guarantee. Local rebalancing does not establish a global optimum.
- Population and final part-graph traversals were recomputed; full saved polygon components and source endpoint ownership were rechecked. Statewide source-coverage equality reuses the preserved independent exporter audit.
- Objective improvement is comparable within each inner pass only. Trace populations are intermediate point assignments before whole-block connectivity repair.
- Wall timings include tracing and shared-desktop contention; peak memory is per-process OS peak working set; gzip file sizes do not measure browser memory or network latency.
