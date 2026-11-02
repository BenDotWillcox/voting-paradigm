# Hawaii: population-aware island-water connections

**Connectivity passes; population balance varies sharply. K2 exceeds 1% deviation and should not be presented as a balanced plan.**

All three requested plans pass polygon-part and independent polygon connectivity **under their recorded water policy**. That terminal status does not certify population quality. All **14,732 blocks and 1,455,271 residents** remain covered exactly. The original strict results, source archive and national manifest remain byte-identical.

[Comparison](http://127.0.0.1:8770/policies/hawaii-water-v1/) · [Original source diagnosis](http://127.0.0.1:8770/diagnostics/hawaii/). Maps open on the main islands; **Full northwest extent** shows retained remote coverage. Magenta dashed lines are used within a district; gray selected links are not. **Inspect connection** shows exact endpoint blocks. Neither kind is land.

| Plan | House sizes | Final populations | Maximum deviation | Full pipeline | Peak working set |
|---|---|---|---:|---:|---:|
| [2 districts](http://127.0.0.1:8770/policies/hawaii-water-v1/states/15/districts-2/) | 435 | 1,100,542 / 354,729 | 51.249080% (372,906.500 people) | 53.66 s | 185.3 MiB |
| [3 districts](http://127.0.0.1:8770/policies/hawaii-water-v1/states/15/districts-3/) | 574, 692 | 485,089 / 485,091 / 485,091 | 0.000275% (1.333 people) | 54.56 s | 185.8 MiB |
| [4 districts](http://127.0.0.1:8770/policies/hawaii-water-v1/states/15/districts-4/) | 1000 | 363,818 / 363,817 / 363,818 / 363,818 | 0.000206% (0.750 person) | 54.52 s | 186.8 MiB |

- **K2: 51.249080% maximum deviation.** 6/6 inner optimizer passes failed (ABNORMAL:); 6 failures completed zero iterations. Rebalancing made 0 moves and stopped at `local_optimum`.

K3 and K4 had no failed inner passes. K4 reaches the best possible integer-population balance; K3 is within 1⅓ people of ideal. K2's reported center convergence does not establish successful population balancing, and its local repair stop does not prove a better plan impossible.

**K2 diagnostic:** With K2's saved centers fixed, the original coordinates/default line search again stopped ABNORMAL after 0 iterations. Expressing the same geometry in kilometers (coordinates divided by 1,000) succeeded in 7 iterations: 727,554, 727,717 people, 81.5 people maximum deviation. Keeping the original coordinates and increasing the line-search limit to 100 also reached 81.5 people deviation. This is evidence of numerical scaling and line-search sensitivity in the inner solver. It is an inner-solve diagnostic only: no corrected connected plan, full benchmark or source change was made. The next fix should nondimensionalize the inner objective and weights, report inner optimizer failure explicitly, then rerun repair and independent connectivity validation. [Saved diagnostic](http://127.0.0.1:8770/policies/hawaii-water-v1/diagnostics/k2-conditioning.json). Its timings are separate from the benchmark table.

Population balance is separate from connectivity. The new rule first identifies original components with at least **99% of one ideal district's population**. It tries small-island attachments and mergers of those larger roots, keeping the greatest number of separate groups whose populations admit whole-number district allocations within **1% of the statewide ideal**. Distance breaks ties among the feasible groupings using deterministic constrained spanning forests; this is not a globally optimal geometric network.

For K2/K3/K4, **Oʻahu is the only eligible root**. All 17 physical components therefore join one group through 16 selected connections. Oʻahu can still contain several districts; being a root does not make it one district. Larger islands can remain separate at other counts only when that group's population fits its allocated district count. The 1% group check is a necessary preflight budget, **not final-plan acceptance** or a whole-block balance guarantee.

The larger-island behavior is visible in these **preflight illustrations only; no K8/K10 district plans were run**:

| Hawaii districts | Old nearest-only necessary bound | New necessary bound | Separate groups | Allocated districts |
|---|---:|---:|---:|---|
| 8 (hypothetical) | 10.290936% | 0.452768% | 2 | [6, 2] |
| 10 (hypothetical) | 31.068165% | 0.499724% | 2 | [7, 3] |

At K8, changing small-island attachments preserves two root groups. At K10, Oʻahu remains separate while the Hawaiʻi Island and Maui roots merge. These are optimistic bounds on the selected grouping, not achieved district deviations. The new candidate set additionally excludes connections crossing unrelated source interiors; the historical diagnostic candidate set did not. The rule prioritizes keeping feasible groups separate over attaining the lowest possible population bound.

| Districts | Water-policy preparation | Solve | Repair/balance | Independent polygon audit/export |
|---|---:|---:|---:|---:|
| 2 | 14.28 s | 0.109 s | 0.214 s | 37.72 s |
| 3 | 14.13 s | 0.247 s | 0.168 s | 38.86 s |
| 4 | 14.61 s | 0.369 s | 0.199 s | 38.15 s |

Runs were serial, in fresh processes with cached source/physical graphs. Full pipeline includes preparation and all audits/export; this table lists selected phases. These are shared-desktop observations. The original strict K2 run spent **6.9977 seconds rejecting topology before solving**; K3/K4 reused its exception. There are no strict district plans or comparable strict-solver runtimes. With 17 physical components retained, fewer than 17 districts cannot each be physically connected under pure shared edges.

| Districts | Selected / used links | Physical → policy polygon components | Outer iterations / converged | Repair / balance moves | Stop reason |
|---|---|---|---|---|---|
| 2 | 16 / 15 | [15, 2] → [1, 1] | 5 / True | 2 / 0 | local_optimum |
| 3 | 16 / 16 | [13, 1, 5] → [1, 1, 1] | 5 / True | 1 / 4 | local_optimum |
| 4 | 16 / 16 | [1, 2, 4, 13] → [1, 1, 1, 1] | 6 / True | 6 / 11 | local_optimum |

Each district uses only links whose two endpoint blocks belong to it; no route passes through another district. Independent unsimplified polygon validation checks this connectivity and complete coverage, separately from physical connectivity and display simplification. All water and zero-population blocks remain. Candidate endpoints minimize boundary gaps in a local plane per pair; lengths are spherical endpoint distances, not certified shortest geodesics, shoreline gaps or ferry routes.

347 regression tests passed. All run artifact hashes and original preservation inventories were verified. All three maps were checked in-browser: national, state and exact outlines; used/unused links; K2 county 005 loaded its 50 blocks on demand; K3 connection inspection and full-northwest/main-island views; K4 district selection and link show/hide. The comparison page and its navigation links were verified.

Evidence: [K2 benchmark](C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/policies/hawaii-water-v1/states/15/districts-2/benchmark.json) · [K3 benchmark](C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/policies/hawaii-water-v1/states/15/districts-3/benchmark.json) · [K4 benchmark](C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/policies/hawaii-water-v1/states/15/districts-4/benchmark.json) · [Comparison JSON](C:/Users/benja/projects/voting_paradigm/prompts/hawaii-water-benchmark.json) · [Runner](C:/Users/benja/projects/voting_paradigm/scripts/benchmark_hawaii_water.py). Reports preserve code/source hashes, assignments, move audits, exact connection endpoints, population-allocation decisions and compressed payload sizes. Source archive SHA-256: `c29683118cd7eada4bd4672e30de6bdd5638a752c1d0f7f795b4dd580c02259e`.
