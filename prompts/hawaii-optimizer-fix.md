# Hawaii K2: numerical optimizer correction

The rerun passes every inner optimizer call, polygon-part connectivity and independent unsimplified polygon validation under the **unchanged recorded water policy**. Final maximum population deviation is **0.001992756% (14.500 people)**. Local rebalancing stopped short of the 0.5-person integer-population lower bound. That bound ignores indivisible blocks; the local stop does not establish a global optimum.

[Comparison](http://127.0.0.1:8770/corrections/hawaii-optimizer-v1/) · [Corrected map](http://127.0.0.1:8770/corrections/hawaii-optimizer-v1/states/15/districts-2/) · [Preserved original map](http://127.0.0.1:8770/policies/hawaii-water-v1/states/15/districts-2/) · [Original three-plan comparison](http://127.0.0.1:8770/policies/hawaii-water-v1/).

| Run | Final populations | Maximum deviation | Full pipeline | Peak working set | Failed / total inner passes |
|---|---|---|---:|---:|---:|
| Original water-policy run | 1,100,542 / 354,729 | 51.249080068% (372,906.500 people) | 53.66 s | 185.3 MiB | 6/6 |
| Corrected optimizer | 727,650 / 727,621 | 0.001992756% (14.500 people) | 54.78 s | 183.9 MiB | 0/5 |

The original inner optimizer stopped `ABNORMAL` without advancing, despite reported convergence of center movement. The correction removes irrelevant per-block distance offsets, normalizes remaining squared costs and population mass, and subtracts a common offset from the weights. Zero-population units remain assigned but do not set the population objective's scale. Public centers and weights retain their original units. The line-search limit is also raised to **100**; unsuccessful or nonfinite optimizer output now raises an explicit failure instead of returning a completed plan.

Source, seed, outer/inner iteration budgets and exact water-connection records are retained. Old/new code hashes differ deliberately and are recorded. The earlier fixed-center diagnostic is not used as a full-runtime or connected-plan baseline.

| Run | Selected / used links | Physical → policy polygon components | Repair / rebalance moves | Stop |
|---|---|---|---|---|
| Original water-policy run | 16/15 | [15, 2] → [1, 1] | 2/0 | local_optimum |
| Corrected optimizer | 16/16 | [13, 5] → [1, 1] | 1/1 | local_optimum |

All **14,732 census blocks and 1,455,271 residents** remain covered exactly. No source polygons or water connections changed. A selected connection counts within a district only if both endpoint blocks belong to it; the map distinguishes used magenta links from unused gray links. Physical separation across water remains reported separately from policy connectivity.

| Phase | Original | Corrected |
|---|---:|---:|
| source acquisition | 0.023 s | 0.024 s |
| source extraction | 0.092 s | 0.035 s |
| load and validate blocks | 0.253 s | 0.246 s |
| load or build physical part graph | 0.189 s | 0.188 s |
| prepare population aware water connections | 14.275 s | 14.448 s |
| solve | 0.109 s | 0.132 s |
| audit initial plan | 0.128 s | 0.137 s |
| repair and rebalance | 0.214 s | 0.187 s |
| save and audit final plan | 0.284 s | 0.327 s |
| independent polygon validation and map export | 37.718 s | 38.642 s |
| write viewer and verify preservation | 0.121 s | 0.219 s |

Both pipelines used fresh processes and warm source/physical-graph caches, running serially on the shared desktop at different times. Timings include preparation, policy construction, solving, repair, independent audits and export. They are not isolated hardware comparisons. Process imports, initial preservation inventories and final report flushes are outside the pipeline timer.

372 regression tests passed. Saved benchmark, compressed-map, preserved original artifacts and baseline-code hashes were verified. Browser checks passed for the corrected map: national and exact outlines, main-island extent, inspection of connection hi-water-005 and its endpoints, and navigation to the comparison. The comparison was readable and matched the saved report. Static type checking could not run because mypy is not installed in the project environment.

Verification checked all 18 compressed map artifacts against their recorded decompressed hashes. The new preservation inventory covers 84 files, including the entire prior Hawaii policy output, its saved reports and diagnostics, original strict results, national manifest and source archive. They remain byte-identical. Snapshots of the [original algorithm](http://127.0.0.1:8770/corrections/hawaii-optimizer-v1/baseline-code/districting/algorithm.py) and [original benchmark runner](http://127.0.0.1:8770/corrections/hawaii-optimizer-v1/baseline-code/scripts/benchmark_hawaii_water.py) also match the original benchmark's code hashes.

Evidence: [Original benchmark](C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/policies/hawaii-water-v1/states/15/districts-2/benchmark.json) · [Corrected benchmark](C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/corrections/hawaii-optimizer-v1/states/15/districts-2/benchmark.json) · [Comparison JSON](C:/Users/benja/projects/voting_paradigm/prompts/hawaii-optimizer-fix.json).
