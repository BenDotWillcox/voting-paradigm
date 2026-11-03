# Hawaii K3/K4: fixed-optimizer reruns

Both requested plans completed with every inner optimizer pass successful. All 14,732 census blocks and 1,455,271 residents are covered exactly. The original strict and water-policy results, and the prior corrected K2 results, remain byte-identical. Each K retains its own exact original water-connection record.

[Interactive comparison](http://127.0.0.1:8770/corrections/hawaii-optimizer-v1/anchors-3-4/) · [Previous K2 correction](http://127.0.0.1:8770/corrections/hawaii-optimizer-v1/) · [Original three-plan comparison](http://127.0.0.1:8770/policies/hawaii-water-v1/).

The original K3/K4 plans already had excellent final balance. The corrected optimizer is the same normalization, line-search limit and explicit failure handling used for corrected K2. No numerical or island-policy changes were made for these reruns. Seed, outer/inner iteration limits and connectivity-repair budget match each preserved original. Every new inner call succeeds; center convergence and final population quality remain separate outcomes.

3-district maximum deviation rose from 1.333 to 2.667 people; 4-district maximum deviation rose from 0.750 to 10.750 people. The preserved originals remain better balanced at both counts. Connectivity still passes in both plans. These are local rebalancing results, not evidence of a globally optimal whole-block partition.

## 3 districts

[Corrected map](http://127.0.0.1:8770/corrections/hawaii-optimizer-v1/states/15/districts-3/) · [Preserved original map](http://127.0.0.1:8770/policies/hawaii-water-v1/states/15/districts-3/)

| Run | District populations | Maximum deviation from ideal | Full pipeline | Numerical solve | Peak working set | Failed / total inner passes |
|---|---|---|---:|---:|---:|---:|
| Original water-policy run | 485,089 / 485,091 / 485,091 | 0.000274863% (1.333 people) | 54.56 s | 0.247 s | 185.8 MiB | 0/6 |
| Corrected optimizer | 485,089 / 485,089 / 485,093 | 0.000549726% (2.667 people) | 56.35 s | 0.293 s | 184.0 MiB | 0/9 |

Local rebalancing stopped short of the 0.666667-person integer-population lower bound. That bound ignores indivisible blocks; the local stop does not establish a global optimum. The original initial solver deviation was 0.023157199%; the corrected initial solver deviation is 0.038893100%. The table above reports final populations after connectivity repair and rebalancing.

| Run | Physical polygon components | Policy polygon components | Selected / used links | Repair / balance moves | Stop |
|---|---|---|---|---|---|
| Original water-policy run | [13, 1, 5] | [1, 1, 1] | 16/16 | 1/4 | local_optimum |
| Corrected optimizer | [13, 1, 5] | [1, 1, 1] | 16/16 | 1/6 | local_optimum |

All 3 districts pass both polygon-part graph validation and independent unsimplified polygon validation under the water policy. A component count greater than one in the physical column remains real separation across water. Connections are used only when both endpoint blocks belong to the same district.

| Pipeline phase | Original | Corrected |
|---|---:|---:|
| source acquisition | 0.023 s | 0.022 s |
| source extraction | 0.033 s | 0.032 s |
| load and validate blocks | 0.235 s | 0.252 s |
| load or build physical part graph | 0.187 s | 0.194 s |
| prepare population aware water connections | 14.127 s | 13.970 s |
| solve | 0.247 s | 0.293 s |
| audit initial plan | 0.125 s | 0.134 s |
| repair and rebalance | 0.168 s | 0.191 s |
| save and audit final plan | 0.269 s | 0.352 s |
| independent polygon validation and map export | 38.857 s | 40.496 s |
| write viewer and verify preservation | 0.128 s | 0.232 s |

The corrected preservation inventory verifies 114 files. Original and corrected compressed maps (18 artifacts) match their recorded decompressed hashes. [Original benchmark](C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/policies/hawaii-water-v1/states/15/districts-3/benchmark.json) · [Corrected benchmark](C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/corrections/hawaii-optimizer-v1/states/15/districts-3/benchmark.json).
## 4 districts

[Corrected map](http://127.0.0.1:8770/corrections/hawaii-optimizer-v1/states/15/districts-4/) · [Preserved original map](http://127.0.0.1:8770/policies/hawaii-water-v1/states/15/districts-4/)

| Run | District populations | Maximum deviation from ideal | Full pipeline | Numerical solve | Peak working set | Failed / total inner passes |
|---|---|---|---:|---:|---:|---:|
| Original water-policy run | 363,818 / 363,817 / 363,818 / 363,818 | 0.000206147% (0.750 person) | 54.52 s | 0.369 s | 186.8 MiB | 0/7 |
| Corrected optimizer | 363,821 / 363,821 / 363,822 / 363,807 | 0.002954776% (10.750 people) | 54.51 s | 0.337 s | 185.4 MiB | 0/8 |

Local rebalancing stopped short of the 0.75-person integer-population lower bound. That bound ignores indivisible blocks; the local stop does not establish a global optimum. The original initial solver deviation was 0.150006425%; the corrected initial solver deviation is 0.035388598%. The table above reports final populations after connectivity repair and rebalancing.

| Run | Physical polygon components | Policy polygon components | Selected / used links | Repair / balance moves | Stop |
|---|---|---|---|---|---|
| Original water-policy run | [1, 2, 4, 13] | [1, 1, 1, 1] | 16/16 | 6/11 | local_optimum |
| Corrected optimizer | [1, 2, 4, 13] | [1, 1, 1, 1] | 16/16 | 7/12 | local_optimum |

All 4 districts pass both polygon-part graph validation and independent unsimplified polygon validation under the water policy. A component count greater than one in the physical column remains real separation across water. Connections are used only when both endpoint blocks belong to the same district.

| Pipeline phase | Original | Corrected |
|---|---:|---:|
| source acquisition | 0.023 s | 0.025 s |
| source extraction | 0.033 s | 0.038 s |
| load and validate blocks | 0.232 s | 0.234 s |
| load or build physical part graph | 0.188 s | 0.171 s |
| prepare population aware water connections | 14.611 s | 13.812 s |
| solve | 0.369 s | 0.337 s |
| audit initial plan | 0.135 s | 0.144 s |
| repair and rebalance | 0.199 s | 0.189 s |
| save and audit final plan | 0.287 s | 0.272 s |
| independent polygon validation and map export | 38.147 s | 38.841 s |
| write viewer and verify preservation | 0.131 s | 0.267 s |

The corrected preservation inventory verifies 114 files. Original and corrected compressed maps (18 artifacts) match their recorded decompressed hashes. [Original benchmark](C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/policies/hawaii-water-v1/states/15/districts-4/benchmark.json) · [Corrected benchmark](C:/Users/benja/projects/voting_paradigm/.cache/state-block-benchmark/suite-through-1000/corrections/hawaii-optimizer-v1/states/15/districts-4/benchmark.json).

## Measurement and preservation

Both old and new runs are fresh-process pipelines with warm source and physical-graph caches. They ran serially at different times on a shared desktop, so runtime changes are observations rather than isolated hardware comparisons. Full pipeline time includes policy construction, solving, repair, validation, export and preservation verification; imports, initial preservation inventories and final report flush are excluded.

The original full water-policy tree, source archive, strict reports, national manifest and corrected K2 evidence were verified against the new preservation inventories. Saved copies of the old algorithm and benchmark runner match each original report's hashes. New solver and policy code hashes match the corrected K2 benchmark. The saved source polygons and water connections are unchanged; dashed map lines are declared graph connections, not added land.

All 381 districting and benchmark tests passed. Browser checks verified the corrected K3 overview and exact outlines, district population selection, and the corrected K4 overview and recorded water-connection inspector. All 12 comparison links returned HTTP 200. Saved benchmark, compressed map, original source-code snapshot and preservation hashes were verified.

[Machine-readable comparison](C:/Users/benja/projects/voting_paradigm/prompts/hawaii-optimizer-anchors.json).
